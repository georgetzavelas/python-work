#!/bin/python

"""
Script to take a file in the format:
Line 1
Line 2
Line 3
Line 4
Line 5
Line 6
Line 7
Line 8

and turn it into
Line1,Line2,Line3,Line4
Line5,Line6,Line7,Line8

TODO:
- get rid of unnecessary lines
- look for files in subdirectories
"""

import os

output_file = open('AccessAlarms.txt', 'w')
for doc in os.listdir('.'):
	if (doc.startswith('AccessAlarms')):
		with open(doc, 'r') as z:
			lines_iter = iter(z.read().splitlines())  # If z is a file, lines_iter = z works			
			# itertools.izip() is usable, too, for a low memory footprint:
			for date_time_order in zip(lines_iter, lines_iter, lines_iter, lines_iter):
	 			output_file.write(','.join(date_time_order))  # "<date> <time> <order>"
	 			output_file.write('\n')
