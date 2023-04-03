import random
from iteration_utilities import random_product


t1 = random.sample(range(1,9), 8)
t2 = random.sample(range(10,100), 90)
sample_size = 700
r = random_product(t1, t2, repeat = sample_size)

f = open("questions.csv", 'w')
f.write("term1,term2,answer\n")

for i in range(0,sample_size):
    f.write(f'{r[i*2]},{r[i*2 + 1]},{r[i*2]*r[i*2 + 1]}\n')

f.close()

