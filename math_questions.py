import pandas as pd
import sys

df = pd.read_csv('questions.csv')
df = df.reset_index()

score = 0
for index, row in df.iterrows():
	answer = input(f"{row['term1']} * {row['term2']} = ")
	try:
		if int(answer) == int(row['answer']):
			print('Correct!')
			score += 1
		else:
			print('Incorrect')
	except ValueError:
		if answer == 'q':
			break
		else:
			print("Please input an integer")
	print('Current Score:', score)

#If command line args are given:
#Writes out "arg2: score" to the file "arg1"		
if len(sys.argv) > 2:
	f = open(sys.argv[1], 'a')
	f.write(f'{sys.argv[2]}: {score}\n')
	f.close()
	print(f"Score written to {sys.argv[1]}")
