from time import time
from .path import single_source_shortest_path
from .classes import Column
from .consts import MIN_OD_VOL


__all__ = ['perform_odme','perform_network_assignment']


def _update_generalized_link_cost(spnetworks):
    """ update generalized link costs for each SPNetwork

    warning: there would be duplicate updates for SPNetworks with the same tau
    and vot belonging to different memory blocks. It could be resolved by
    creating a shared network among them??
    """
    for sp in spnetworks:
        tau = sp.get_demand_period().get_id()
        vot = sp.get_agent_type().get_vot()

        for link in sp.get_links():
            sp.link_cost_array[link.get_seq_no()] = (
            link.get_period_travel_time(tau)
            + link.get_route_choice_cost()
            + link.get_toll() / min(0.001, vot) * 60
        )


def _update_link_travel_time_and_cost(links):
    for link in links:
        link.calculate_td_vdfunction()
        # Peiheng, 04/05/21, not needed for the current implementation
        # for dp in demand_periods:
        #     tau = dp.get_id()
        #     for at in agent_types:
        #         link.calculate_agent_marginal_cost(tau, at)


def _reset_and_update_link_vol_based_on_columns(column_pool,
                                                links,
                                                demand_periods,
                                                iter_num,
                                                is_path_vol_self_reducing):

    # the original implementation is iter_num < 0, which does not make sense
    if iter_num == 0:
        return

    for link in links:
        for dperiod in demand_periods:
            tau = dperiod.get_id()
            link.reset_period_flow_vol(tau)
            # Peiheng, 04/05/21, not needed for the current implementation
            # link.queue_length_by_slot[tau] = 0
            # for atype in agent_types:
            #     link.reset_period_agent_vol(tau, atype.get_id())


    for k, cv in column_pool.items():
        if cv.get_od_volume() <= 0:
            continue

        # k= (at, tau, oz_id, dz_id)
        tau = k[1]

        for col in cv.get_columns().values():
            link_vol_contributed_by_path_vol = col.get_volume()
            for i in col.links:
                pce_ratio = 1
                links[i].increase_period_flow_vol(
                    tau,
                    link_vol_contributed_by_path_vol * pce_ratio
                )
                # Peiheng, 04/05/21, not needed for the current implementation
                # links[i].increase_period_agent_vol(
                #     tau,
                #     at,
                #     link_vol_contributed_by_path_vol
                # )

            if not cv.is_route_fixed() and is_path_vol_self_reducing:
                col.vol *= iter_num / (iter_num + 1)



def _update_column_gradient_cost_and_flow(column_pool,
                                          links,
                                          agent_types,
                                          demand_periods,
                                          iter_num):

    _reset_and_update_link_vol_based_on_columns(column_pool,
                                                links,
                                                demand_periods,
                                                iter_num,
                                                False)

    _update_link_travel_time_and_cost(links)

    total_gap = 0
    # total_gap_count = 0

    for k, cv in column_pool.items():
        if cv.get_od_volume() <= 0:
            continue

        # k= (at, tau, oz_id, dz_id)
        vot = agent_types[k[0]].get_vot()
        tau = k[1]

        column_num = cv.get_column_num()
        least_gradient_cost = 999999
        least_gradient_cost_path_seq_no = -1
        least_gradient_cost_path_node_sum = -1

        for node_sum, col in cv.get_columns().items():
            path_toll = 0
            path_gradient_cost = 0
            path_travel_time = 0
            # i is link sequence no
            for i in col.get_links():
                path_toll += links[i].get_toll()
                path_travel_time += (
                    links[i].travel_time_by_period[tau]
                )
                path_gradient_cost += (
                    links[i].get_generalized_cost(tau, vot)
                )

            col.set_toll(path_toll)
            col.set_travel_time(path_travel_time)
            col.set_gradient_cost(path_gradient_cost)

            if column_num == 1:
                # total_gap_count += (
                #     path_gradient_cost * col.get_volume()
                # )
                break

            if path_gradient_cost < least_gradient_cost:
                least_gradient_cost = path_gradient_cost
                least_gradient_cost_path_seq_no = col.get_seq_no()
                least_gradient_cost_path_node_sum = node_sum

        if column_num >= 2:
            total_switched_out_path_vol = 0

            for col in cv.get_columns().values():
                if col.get_seq_no() == least_gradient_cost_path_seq_no:
                    continue

                col.set_gradient_cost_abs_diff(
                    col.get_gradient_cost() - least_gradient_cost
                )
                col.set_gradient_cost_rel_diff(
                    col.get_gradient_cost_abs_diff()
                    / max(0.0001, least_gradient_cost)
                )

                total_gap += (
                    col.get_gradient_cost_abs_diff() * col.get_volume()
                )

                # total_gap_count += (
                #     col.get_gradient_cost() * col.get_volume()
                # )

                step_size = 1 / (iter_num + 2) * cv.get_od_volume()

                previous_path_vol = col.get_volume()
                col.vol = max(
                    0,
                    (previous_path_vol
                     - step_size
                     * col.get_gradient_cost_rel_diff())
                )

                col.set_switch_volume(previous_path_vol - col.get_volume())
                total_switched_out_path_vol += col.get_switch_volume()

        if least_gradient_cost_path_seq_no != -1:
            col = cv.get_column(least_gradient_cost_path_node_sum)
            col.increase_volume(total_switched_out_path_vol)
            # total_gap_count += (
            #     col.get_gradient_cost() * col.get_volume()
            # )

    print(f'total gap: {total_gap:.2f}')
    # print(f'total gap count is: {total_gap_count:.2f}')


def _optimize_column_pool(column_pool,
                          links,
                          agent_types,
                          demand_periods,
                          colum_update_num):

    for i in range(colum_update_num):
        print(f"current iteration number in column generation: {i}")
        _update_column_gradient_cost_and_flow(column_pool,
                                              links,
                                              agent_types,
                                              demand_periods,
                                              i)


def _backtrace_shortest_path_tree(orig_node_no,
                                  nodes,
                                  links,
                                  node_preds,
                                  link_preds,
                                  node_label_costs,
                                  agent_type,
                                  demand_period,
                                  column_pool,
                                  iter_num):

    if not nodes[orig_node_no].has_outgoing_links():
        return

    oz_id = nodes[orig_node_no].get_zone_id()
    k_path_prob = 1 / (iter_num + 1)

    for node in nodes:
        i = node.get_node_no()
        if i == orig_node_no:
            continue

        dz_id = node.get_zone_id()
        if dz_id == -1:
            continue

        if (agent_type, demand_period, oz_id, dz_id) not in column_pool.keys():
            continue

        cv = column_pool[(agent_type, demand_period, oz_id, dz_id)]
        if cv.is_route_fixed():
            continue

        od_vol = cv.get_od_volume()
        if od_vol <= MIN_OD_VOL:
            continue

        vol = od_vol * k_path_prob

        node_path = []
        link_path = []

        dist = 0
        node_sum = 0
        current_node_seq_no = i
        # retrieve the sequence backwards
        while current_node_seq_no >= 0:
            node_path.append(current_node_seq_no)
            node_sum += current_node_seq_no

            current_link_seq_no = link_preds[current_node_seq_no]
            if current_link_seq_no >= 0:
                link_path.append(current_link_seq_no)
                dist += links[current_link_seq_no].length

            current_node_seq_no = node_preds[current_node_seq_no]

        # make sure this is a valid path
        if not link_path:
            continue

        if node_sum not in cv.path_node_seq_map.keys():
            path_seq_no = cv.get_column_num()
            col = Column(path_seq_no)
            col.set_toll(node_label_costs[i])
            col.nodes = [x for x in node_path]
            col.links = [x for x in link_path]
            col.set_distance(dist)
            cv.add_new_column(node_sum, col)

        cv.get_column(node_sum).increase_volume(vol)


def _update_column_travel_time(column_pool, links):

    for k, cv in column_pool.items():
        if cv.get_od_volume() <= 0:
            continue

        # k = (at, dp, oz, dz)
        dp = k[1]

        for col in cv.get_columns().values():
            travel_time = sum(
                links[j].travel_time_by_period[dp] for j in col.links
            )
            col.set_travel_time(travel_time)

def _assignment_core(spn, column_pool, iter_num):

    for node_id in spn.get_orig_nodes():
        single_source_shortest_path(spn, node_id)

        _backtrace_shortest_path_tree(spn.get_node_no(node_id),
                                      spn.get_nodes(),
                                      spn.get_links(),
                                      spn.get_node_preds(),
                                      spn.get_link_preds(),
                                      spn.get_node_label_costs(),
                                      spn.get_agent_type().get_id(),
                                      spn.get_demand_period().get_id(),
                                      column_pool,
                                      iter_num)

def _assignment(spnetworks, column_pool, iter_num):
    # single processing
    # it could be multiprocessing
    for spn in spnetworks:
        _assignment_core(spn, column_pool, iter_num)

def perform_network_assignment(assignment_mode, iter_num, column_update_num, ui):
    """ perform network assignemnt using the selected assignment mode

    WARNING
    -------
        Only Path/Column-based User Equilibrium (UE) is implemented in Python.
        If you need other assignment modes or dynamic traffic assignment (DTA),
        please use perform_network_assignment_DTALite()

    Parameters
    ----------
    assignment_mode
        0: Link-based UE
        1: Path-based UE
        2: UE + dynamic traffic assignment and simulation
        3: ODME
    iter_num
        number of assignment iterations to be performed before optimizing
        column pool
    column_update_iter
        number of iterations to be performed on optimizing column pool
    ui
        network object generated by pg.read_demand()

    Outputs
    -------
    None

        You will need to call output_columns() and output_link_performance() to
        get the assignment results, i.e., paths/columns (in agent.csv) and
        assigned volumes and other link attributes on each link (in l
        ink_performance.csv)
    """

    # make sure iteration numbers are both non-negative
    assert(iter_num>=0)
    assert(column_update_num>=0)

    # base assignment
    A = ui._base_assignment
    network=A.get_network()
    links = A.get_links()
    nodes =A.get_nodes()
    zones=A.get_zones()

    ats = A.get_agent_types()
    dps = A.get_demand_periods()
    column_pool = A.get_column_pool()

    st = time()

    if assignment_mode == 1:    #path-based ue 
        for i in range(iter_num):
            print(f"current iteration number in assignment: {i}")
            _update_link_travel_time_and_cost(links)

            _reset_and_update_link_vol_based_on_columns(column_pool,
                                                        links,
                                                        dps,
                                                        i,
                                                        True)

            # update generalized link cost before assignment
            _update_generalized_link_cost(A.get_spnetworks())

            # loop through all nodes on the base network
            _assignment(A.get_spnetworks(), column_pool, i)

        print(f'\nprocessing time of assignment: {time()-st:.2f} s')

        _optimize_column_pool(column_pool, links, ats, dps, column_update_num)

        _reset_and_update_link_vol_based_on_columns(column_pool,
                                                    links,
                                                    dps,
                                                    iter_num,
                                                    False)

        _update_link_travel_time_and_cost(links)

        _update_column_travel_time(column_pool, links)

    else:
        raise Exception("not implemented yet")
    
def perform_odme(iter_num, column_update_num, ui, ue_flag=False):

    A = ui._base_assignment
    network=A.get_network()
    links = A.get_links()
    nodes =A.get_nodes()
    zones=A.get_zones()

    ats = A.get_agent_types()
    dps = A.get_demand_periods()
    column_pool = A.get_column_pool()

    st = time()
    
    #read measurement and perform traffic assignment
    perform_network_assignment(1, iter_num, column_update_num, ui)


    #loop for adjusting OD demand
    for s in range(iter_num):
        total_gap = 0
        total_relative_gap = 0
        total_gap_count = 0
        
        #we can have a recursive formulat to reupdate the current link volume by a factor of k/(k+1),
        #and use the newly generated path flow to add the additional 1/(k+1)
        _reset_and_update_link_volume_based_on_ODME_columns(column_pool,nodes,links,zones,network.zone_to_nodes_dict,
                                            dps,ats,s,network.zone_id_to_zone_dict)
        if ue_flag:
            #based on newly calculated path volumn, update volume based travel time, and update volume based measurement error/deviation
            _update_link_travel_time_and_cost(links)
            #calculate shortest path at inner iteration of column flow updating
            _assignment(A.get_spnetworks(), column_pool, 1)

        _od_adjust(column_pool,nodes,links,network.zone_to_nodes_dict,s,network.zone_id_to_zone_dict)



def update_links_using_columns(network):
    """ a helper function for load_columns() """
    A = network._base_assignment

    column_pool = A.get_column_pool()
    links = A.get_links()
    dps = A.get_demand_periods()

    # do not update column volume
    _reset_and_update_link_vol_based_on_columns(column_pool,
                                                links,
                                                dps,
                                                1,
                                                False)

    _update_link_travel_time_and_cost(links)

def _reset_and_update_link_volume_based_on_ODME_columns(column_pool,nodes,links,zones,zone_to_node_dict,
                                                       demand_periods,agent_types,iter_num,zone_id_to_zone_dict):
    total_gap = 0
    sub_total_gap_link_count = 0
    sub_total_gap_P_count = 0
    sub_total_gap_A_count = 0

    link_size=len(links)
    #reset the link volume
    for link in links:
        for dperiod in demand_periods:
            tau = dperiod.get_id()
            link.reset_period_flow_vol(tau)

    #reset the estimated production and attraction
    for zone in zones:
        zone_id_to_zone_dict[zone].est_attraction = 0
        zone_id_to_zone_dict[zone].est_production = 0


    for k, cv in column_pool.items():
        if cv.get_od_volume() <= 0:
            continue
        # k= (at, tau, oz_id, dz_id)
        tau = k[1]
        o_zone= k[2]
        d_zone= k[3]

        for col in cv.get_columns().values():
            link_vol_contributed_by_path_vol = col.get_volume()
            zone_id_to_zone_dict[o_zone].est_production+=link_vol_contributed_by_path_vol
            zone_id_to_zone_dict[d_zone].est_attraction+=link_vol_contributed_by_path_vol

            for i in col.links:
                pce_ratio = 1
                links[i].increase_period_flow_vol(
                    tau,
                    link_vol_contributed_by_path_vol * pce_ratio
                )

    #calcualte deviation for each measurement type
    for link in links:
        link.calculate_td_vdfunction()
        if link.obs_count>0:  #with data
            tau = 0
            link.est_count_dev = link.obs_count-link.flow_vol_by_period[tau]
            total_gap += abs(link.est_count_dev)
            sub_total_gap_link_count += link.est_count_dev / link.obs_count

    for zone in zones:
        if zone_id_to_zone_dict[zone].obs_attraction >0:
            zone_id_to_zone_dict[zone].est_attraction_dev=zone_id_to_zone_dict[zone].obs_attraction-zone_id_to_zone_dict[zone].est_attraction
            total_gap+=abs(zone_id_to_zone_dict[zone].est_attraction_dev)
            sub_total_gap_A_count+=zone_id_to_zone_dict[zone].est_attraction_dev/zone_id_to_zone_dict[zone].obs_attraction
        if zone_id_to_zone_dict[zone].obs_production >0:
            zone_id_to_zone_dict[zone].est_production_dev=zone_id_to_zone_dict[zone].obs_production-zone_id_to_zone_dict[zone].est_production
            total_gap+=abs(zone_id_to_zone_dict[zone].est_production_dev)
            sub_total_gap_P_count+=zone_id_to_zone_dict[zone].est_production_dev/zone_id_to_zone_dict[zone].obs_production

    print("ODME adjust iter {0}: total abs gap= {1}, sub link gap= {2}, sub production gap= {3}, sub attraction gap= {4}".format(iter_num,
                  total_gap,sub_total_gap_link_count*100,sub_total_gap_P_count*100,sub_total_gap_A_count*100))

def _od_adjust(column_pool,nodes,links,zone_to_node_dict,iter_num,zone_id_to_zone_dict):

    for k, cv in column_pool.items():
        if cv.get_od_volume() <= 0:
            continue
        # k= (at, tau, oz_id, dz_id)
        tau = k[1]
        o_zone= k[2]
        d_zone= k[3]

        for col in cv.get_columns().values():
            path_gradient_cost = 0
            path_distance = 0
            path_travel_time = 0

            #origin production flow gradient
            if zone_id_to_zone_dict[o_zone].obs_production >0:
                path_gradient_cost += zone_id_to_zone_dict[o_zone].est_production_dev

            #destination attraction flow gradient
            if zone_id_to_zone_dict[d_zone].obs_attraction >0:
                path_gradient_cost += zone_id_to_zone_dict[d_zone].est_attraction_dev
           
            #link flow gradient
            for i in col.links:
                if links[i].obs_count>0:
                    path_gradient_cost+=links[i].est_count_dev

            col.path_gradient_cost=path_gradient_cost
            step_size = 0.01
            prev_path_volume = col.vol
            change = step_size * col.path_gradient_cost
            change_lower_bound = col.vol * 0.05 * (-1)
            change_upper_bound = col.vol * 0.05 

            #reset
            if (change < change_lower_bound):
                change = change_lower_bound
            #reset
            if (change > change_upper_bound):
                change = change_upper_bound

            col.vol = max(1, col.vol + change);






