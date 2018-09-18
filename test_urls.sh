#!/bin/bash

# open URLs from file in browser:
# open in chrome each pair of URLs in a file containing a pair of URLs separated by a comma on each line

# take file as first argument
filename=$1

# keep track of line number, declare it as an int
linenr=1

for line in $(cat $filename)
do
	# if there's a match
	if [[ "$line" == *,* ]]
		then
		echo "$line" | cut -d',' -f1 | xargs google-chrome
		echo "$line" | cut -d',' -f2 | xargs google-chrome
		third=`echo "$line" | cut -d',' -f3`
		if [ -n "$third" ]
		then
			echo "$third" | xargs google-chrome
		fi
	# if there's only one result
	else
		google-chrome "$line"
	fi


	# print current line number
	echo $linenr
	linenr=$((1+linenr))

	# wait for user input before opening next pairs of urls
	read aux
done