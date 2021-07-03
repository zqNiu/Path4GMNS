import path4gmns as pg
from time import time

def test_column_generation():
    network = pg.read_network()

    print('\nstart column generation\n')
    st = time()

    iter_num = 30
    column_update_num = 30
    # pg.perform_network_assignment(assignment_mode=1, assignment_num,
    #                               column_update_num, network)

    pg.perform_network_assignment(1,iter_num, column_update_num, network)

    print(f'processing time of column generation: {time()-st:.2f} s'
          f' for {iter_num} assignment iterations and '
          f'{column_update_num} iterations in column generation')

    # if you do not want to include geometry info in the output file,
    # use pg.output_columns(network, False)
    pg.output_columns(network)
    pg.output_link_performance(network)
    pg.output_path_link_propotion(network)
    pg.output_od_path_propotion(network)
    pg.output_od_link_propotion(network)

if __name__=="__main__":

    test_column_generation()
