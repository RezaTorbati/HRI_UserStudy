import pandas as pd
import sys
import os

def run_program(id):
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

	#Saves the score	
	f = open(f"logs/{id}/{id}_math_score.txt", 'w')
	f.write(str(score))
	f.close()
	#print(f"Score written to {sys.argv[1]}")
	print("Final score:", score)

if __name__=="__main__":
	f = open("participantID.txt", "r")
	id = str.strip(f.read())
	f.close()
	if not os.path.exists(f'logs/{id}'):
		os.makedirs(f"logs/{id}")
	run_program(id)
