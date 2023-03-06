import pandas as pd

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
		print("Please input an integer")
	print('Current Score:', score)
		

