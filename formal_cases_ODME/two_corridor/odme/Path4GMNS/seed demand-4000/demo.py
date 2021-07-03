import path4gmns as pg
from time import time

def test_odme():
    network = pg.read_network()

    print('\nstart column generation\n')
    st = time()

    iter_num = 20
    column_update_num = 100

    pg.perform_odme(iter_num, column_update_num, network)

    print(f'processing time of column generation: {time()-st:.2f} s'
          f' for {iter_num} assignment iterations and '
          f'{column_update_num} iterations in column generation')

    pg.output_odme_performance(network)

if __name__=="__main__":

    test_odme()
