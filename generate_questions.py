import random
from iteration_utilities import random_product


t1 = random.sample(range(10,100), 90)
t2 = random.sample(range(10,100), 90)
r = random_product(t1, t2, repeat = 2000)

f = open("questions.csv", 'w')
f.write("term1,term2,answer\n")

for i in range(0,2000):
    f.write(f'{r[i]},{r[i+2000]},{r[i]*r[i+2000]}\n')

f.close()

