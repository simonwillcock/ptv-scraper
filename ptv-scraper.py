from __future__ import print_function
from bs4 import BeautifulSoup
from urllib2 import urlopen
from urllib import urlencode
import sqlite3
from os import remove
import re
from pprint import pprint
import logging

BASE_URL = "http://ptv.vic.gov.au/timetables"
BASE_STOPS_URL = "http://ptv.vic.gov.au/timetables/line/%s"
BASE_TIMETABLE_URL = "http://ptv.vic.gov.au/timetables/linemain/%s"
BASE_LINE_URL = "http://ptv.vic.gov.au/route/view/"
STOP_URL = "http://ptv.vic.gov.au/stop/view/"
STOP_SUBURB_LIST = "http://ptv.vic.gov.au/getting-around/stations-and-stops/metropolitan-trains/"
TEST_RUN = False

STOP_SKIPPED = "|"
STOP_IGNORE = " "
STOP_NOT_IN_RUN = "-"



def populate_train_lines(test_run=False):
	# Populate train_lines

	html = urlopen(BASE_URL).read()
	logging.debug(BASE_URL)
	soup = BeautifulSoup(html) # , "lxml"
	line_select = soup.find(id="RouteForm2_RouteUrl")
	
	# Get number and name from select element
	lines = [(line.get("value").replace(BASE_LINE_URL,""), line.getText()) for line in line_select.findAll("option")][1:]

	# Sort by id and remove "line" from the name except for flemington special case
	lines = sorted([(int(x),y) if int(x) == 1482 else (int(x),y[:-5]) for (x,y) in lines], key=lambda tup: tup[0])

	if test_run == False:
		# Add to database (leave suburb list blank for now)
		conn = sqlite3.connect("ptv.db") 
		cursor = conn.cursor()
		defaults = (None,None,None)
		cursor.executemany("INSERT INTO train_lines VALUES (?,?,NULL)", lines)
		conn.commit()

	
		
def populate_stops(test_run=False):
	conn = sqlite3.connect("ptv.db") 
	cursor = conn.cursor()
	lines = cursor.execute("""
		SELECT _id, line_name 
		FROM train_lines
		""").fetchall()

	# 3 letter codes used in POST request
	line_codes = [
		(1,"Alemain","ALM"),
		(2,"Belgrave","BEL"),
		(3,"Craigieburn","BDM"),
		(4,"Cranbourne","CRB"),
		(5,"South Morang","EPP"),
		(6,"Frankston","FKN"),
		(7,"Glen Waverly","GLW"),
		(8,"Hurstbridge","HBG"),
		(9,"Lilydale","LIL"),
		(11,"Pakenham","PKM"),
		(12,"Sandringham","SDM"),
		(13,"Stony Point","SPT"),
		(14,"Sunbury","SYM"),
		(15,"Upfield","UFD"),
		(16,"Werribee","WBE"),
		(17,"Williamstown","WMN"),
		(1482,"Flemington Showgrounds / Flemington Racecourse","AIN"),
	]
	run_id = 0
	for line in lines:
		for code in line_codes:
			if code[0] == line[0]:
				run_id = process_line(line,code,run_id,test_run)

def process_line(line,code,run_id,test_run=False):
	# Load Line page to get line url numbers for each direction
	# print "%s, %s, %s" % (line, code, run_id)

	# html = urlopen(BASE_LINE_URL+str(line[0])).read()
	# soup = BeautifulSoup(html)
	# list_items = soup.find(id="content").findAll("h3")[0].findNext("ul").findAll("li")
	# for item in list_items:
		# anchor = item.find("a", href=True)
		# direction_id = anchor['href'].replace("timetables/line/","")
		# process_stops(direction_id,line,anchor.getText())
	direction_to_city = "R"
	direction_from_city = "H"
	directions = [direction_to_city,direction_from_city]
	print("Processing Stops for the %s Line - %s: " % (line[1],code[0]))

	for direction in directions:
		# print "  - %s" % (direction,)

		soup = get_timetable_page_soup(line, direction, code)

		stop_table = soup.find(id="ttTable")

		# Calculate direction id
		direction_soup = soup.find(id="itdLPxx_selLineDir")
		direction_name = direction_soup.find_all('option', selected=True)[0].get_text().replace("To ","")

		print("   To %s" % direction_name)
		conn = sqlite3.connect("ptv.db")
		cursor = conn.cursor()

		# Special case fix for showgrounds naming differences
		if direction_name == "Showgrounds/Flemington":
			direction_name = "Showgrounds / Flemington Racecourse"
		direction_id = cursor.execute("""
			SELECT _id 
			FROM train_direction 
			WHERE direction_name = ?
			""", (direction_name,)).fetchone()[0]
		run_id = process_stops(stop_table, run_id, code[0], direction_id)
		
	return run_id

def get_timetable_page_soup(line, direction, code):
	# Sometimes the time-periods in the dropdown are different.
	# This will return the soup of the latest time-period
	is_good_data = False
	time_periods = ["D","E","C","B","A"," "]
	while (is_good_data == False):
		
		day = "T0" # Mon-Fri
		
		# Dict of data required for POST request
		post_data_dictionary = {
		'language':'en', 
		"command":'direct', 
		"net":"vic",
		"project":"ttb",
		"contentFilter":"ALLSTOPS",
		"outputFormat":0,
		"line":"02%s" % (code[2],),
		"itdLPxx_selLineDir": direction,
		"sup":time_periods[0],
		"itdLPxx_selWDType":"T0",
		"actionChoose":"GO"
		}

		
		
		data = urlencode(post_data_dictionary)
		
		html = urlopen(BASE_TIMETABLE_URL % line[0], data).read()
		soup = BeautifulSoup(html)

		# Check if time period is valid. Different lines have different options
		# If invalid, page has a string in <strong> tags which is tested below.
		if soup.find("strong") != None:
			del time_periods[0]
			print("  --- Failed. Trying %s" % time_periods[0])
			logging.warning("  --- Failed. Trying %s" % time_periods[0])
		else:
			logging.debug(BASE_TIMETABLE_URL % line[0] + "?" + data)
			return soup


	
	
def process_stops(table_soup, run_id, line_id, direction_id):
	# Get list of stations in line from margin of table
	margin = table_soup.find(id="ttMargin")
	station_list = [x.getText() for x in margin.select(".ttMarginTP .ma_stop a")]
	suburb_regex = re.compile("\((.*)\)")
	name_regex = re.compile("(^.*)(?=\sStation\s\()")

	# Create list of tuples containing station name and suburb
	clean_station_list = []
	for station in station_list:
		suburb = suburb_regex.search(station).groups()[0]
		name = name_regex.search(station).groups()[0]
		clean_station_list.append(name)
		

	# Break table into columns
	tt_body = table_soup.find(id="ttBody")
	rows = tt_body.select(".ttBodyTP")

	# Init variables
	pm = False
	col = 0

	# Calculate total amount of columns
	run_total = len(rows[0].select("div"))

	processed_runs = []
	previous_was_stop = False

	while(col < run_total):
		current_col = []
		# Check if we are in AM or PM section by looking for bold text
		for row in rows:
			cell = row.findAll("div")[col].find("span")
			if cell.find("b") != None:
				pm = True
			else: 
				pm = False
			current_col.append(cell.getText())
		
		conn = sqlite3.connect("ptv.db")
		cursor = conn.cursor()
		
		# Do work with column here
		
		# Set up vars for loop
		# stop_final_format = [line_id, stop_id, run_id, time, destination_id, num_skipped, direction, flags]
		previous_stop = [0,0,0,0,0,0,0,""]

		# Total of cells not in run
		excluded_total = 0

		# Container to hold stop info for run
		final_run = []
		for index, stop in enumerate(current_col):

			# Resets
			time_in_ms = 0

			# Clean up text before processing:
			stop = stop.encode('utf-8').replace('\xc2\xa0'," ")


			if stop == STOP_SKIPPED:
				# Add to count of skipped for most recent stop
				previous_stop[5] += 1

			elif stop == STOP_NOT_IN_RUN and previous_stop[0] != 0:
				# stop isn't in run and the previous stop is not blank
				# meaning it isn't at the start of a run and is just after 
				# a real stop
				if previous_stop[7] != "" and "E" not in previous_stop[7]:
					previous_stop[7] += " E"
				elif "E" not in previous_stop[7]:
					previous_stop[7] = "E"

			elif stop == STOP_NOT_IN_RUN:
				# Not in run and not immediately after a real stop
				excluded_total += 1
			elif stop ==" ":
				# This usually means the run is going the opposite way around the loop.
				1 == 1
			else:
				# We have a real stop to add and already have line_id and run_id 
				
				
				 
				# Get stop_id
				stop_id = cursor.execute("""SELECT train_locations._id 
					FROM train_locations 
					WHERE train_locations.location_name =? """,(clean_station_list[index],)).fetchone()[0]

				if stop_id == 27:
					logging.debug(stop)

				# Calculate time in seconds
				if pm == True:
					# Add 12 hours for conversion
					time_in_ms = convertTimeToMilliseconds(stop,pm)
				else:
					time_in_ms = convertTimeToMilliseconds(stop)

				# Destination will be calculated at end of loop
				# num_skipped is calculated earlier in loop
				# flags is calculated earlier in loop
				 
				# We can now commit the previous stop to the final list
				if previous_stop[0] != 0:
					# Unless it is still blank from init
					final_run.append(previous_stop)

				# Set current stop to previous for next loop
				previous_stop = [line_id, stop_id, run_id, time_in_ms, 0, 0, direction_id, "" ]

			if index == len(current_col) - 1:
				# Final cell in columm 
				# Calculate destination_id and add to final_run results
				
				# Check that we have added end flag in case the run ended at the end of a line
				if previous_stop[7] != "" and "E" not in previous_stop[7]:
					previous_stop[7] += " E"
				elif "E" not in previous_stop[7]:
					previous_stop[7] = "E"

				# Add final stop to run
				final_run.append(previous_stop)

				# Destination = last stop's id
				destination = previous_stop[1]
				for x in final_run:
					x[4] = destination

				# pprint(final_run)

		# Increment loop values for calculations
		col += 1
		run_id += 1

		print("  --- %s/%s runs added" % (col+1,run_total), end='\r') 

		# Commit data to db
		cursor.executemany("""INSERT INTO train_stops_monfri VALUES (?,?,?,?,?,?,?,?)""", final_run)
		conn.commit()

	
	# Return run_id to be used in next line
	return run_id



def convertTimeToMilliseconds(time,pm = False):
	# Converts a time in format xx:x into milliseconds
	# Optional boolean can be passed to indicate time is in PM

	# Split time into 2 parts for calculations
	time_parts = [int(x) for x in time.split(":")]	
	if pm == True:
		return ((time_parts[0] + 12) * 60 * 60) + (time_parts[1] * 60)
	else:
		return (time_parts[0] * 60 * 60) + (time_parts[1] * 60)

def populate_directions(test_run=False):

	# Populate directions	
	if test_run == False:
		conn = sqlite3.connect("ptv.db")
		cursor = conn.cursor()

		# Manually add both flinders st options to match PTV timetable data
		
		directions = [("City (Flinders Street)",)]
		cursor.execute("""SELECT * FROM train_lines""")
		for row in cursor:
			directions.append((row[1],))
		directions.append(("Flinders Street",))

		# Add to db
		cursor.executemany("""INSERT INTO train_direction VALUES (NULL,?)""", directions)
		conn.commit()
		# cursor.execute("""SELECT * FROM train_direction""")
	
def populate_locations(test_run=False):
	# Populate the train_locations table

	html = urlopen(STOP_SUBURB_LIST).read()
	logging.debug(STOP_SUBURB_LIST)
	soup = BeautifulSoup(html)

	suburb_list = soup.select("#alpha-list ul li")
	
	for suburb in suburb_list:
		logging.debug(suburb_list)
		suburb_anchor = suburb.find("a", href=True)
		suburb_name = suburb_anchor.getText()
		print("Processing %s" % suburb_name)
		process_suburb(suburb_anchor['href'], suburb_name, test_run)

	conn = sqlite3.connect("ptv.db")
	cursor = conn.cursor()

	print("===============================\nPopulating linelocation table")
	

	line_locations = []
	
	cursor.execute("""DELETE FROM train_linelocation""")

	locations = cursor.execute("""
		SELECT train_locations._id, train_locations.lines
		FROM train_locations""").fetchall()
	for loc in locations:
		# print loc
		
		lines = loc[1].split("/")
		cleaned_lines = []
		for line in lines:
			if line == "Showgrounds ":
				cleaned_lines.append("Showgrounds / Flemington Racecourse")
			elif line != " Flemington Racecourse":
				cleaned_lines.append(line)

		
		for line in cleaned_lines:
			line_id = cursor.execute("""
			SELECT train_lines._id
			FROM train_lines
			WHERE train_lines.line_name = ?
			""",(line,)).fetchone()
			if line_id != None:
				line_locations.append((line_id[0],loc[0]))
	
	cursor.executemany("""INSERT INTO train_linelocation VALUES (?,?)""", line_locations)
	conn.commit()

def process_suburb(suburb_link, suburb_name, test_run):
	# Get list of stations in suburb
	
	conn = sqlite3.connect("ptv.db")
	cursor = conn.cursor()

	if test_run == True:
		station_results = cursor.execute("""SELECT * FROM train_locations""")
	else:
		html = urlopen(suburb_link).read()
		logging.debug(suburb_link)
		soup = BeautifulSoup(html)
		title = soup.find("h1")
		station_list = title.findNext("ul").findAll("li")

		station_results = []

		for station in station_list:
			station_anchor = station.find("a", href=True)
			station_title = station_anchor.getText()
			station_title_short = station_title.split(" Railway Station", 1)[0]
			print("   Processing station: %s" % station_title_short)
			station_results.append(process_station(station_anchor['href'], station_title_short, suburb_name))
		
	
		cursor.executemany("""INSERT INTO train_locations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", station_results)
		conn.commit()

	
		



def process_station(station_link, station_name, suburb_name):
	# Process station and return list of station properties
	html = urlopen(station_link).read()
	logging.debug(station_link)
	soup = BeautifulSoup(html)

	# Get field data from page
	location_name = station_name
	suburb = suburb_name
	address = soup.find("h1").findNext("div").find("p").getText().strip()
	coordinates = soup.select("div.aside li")[0].find("a", href=True)["href"].replace("http://maps.google.com/?q=","").split(",")
	stop_id = station_link.replace("http://ptv.vic.gov.au/getting-around/stations-and-stops/view/","")

	zone_id = soup.select("table.stationSummary tr")[2].find("td").getText()

	# Zones are either 1,2 or 4 (1/2)
	if zone_id != "1" and zone_id != "2":
		zone_id = 4
	else:
		zone_id = int(zone_id)
	
	# Get extra station info
	staff_box = soup.select("div.phone-numbers")[0].findNextSibling("div")
	staff = staff_box.find("dd").getText()
	ticket_box = staff_box.findNextSibling("div")
	ticket_info = ticket_box.findAll("dd")
	ticket_info = [1 if x.getText() == "Yes" else 0 for x in ticket_info]
	myki_machines = ticket_info[0]
	myki_checks = ticket_info[1]
	vline_bookings = ticket_info[2]
	parking_box = ticket_box.findNextSibling("div")
	car_parking = parking_box.select("dd")[0].getText()
	if parking_box.select("dd")[2].getText() == "Yes":
		taxi = 1
	else:
		taxi = 0

	# Find list of lines that pass through station
	timetables = soup.select("div.expander")
	lines = [line.getText().replace(" Line","") for line in timetables[0].findAll("a")]

	# Create / seperated list of lines for storing in db field
	lines_string = "/".join(lines)
	
	return [None,location_name, suburb, address, coordinates[0], coordinates[1], stop_id, 
	zone_id, staff, myki_machines, myki_checks, vline_bookings, car_parking, taxi, lines_string]

	


def prepare_db(rm_db=True):
	# Create database and tables and add any static data
	# Table primary keys are labelled _id as this is a requirement
	# for databases used in Android apps
	
	# Remove existing db if rm_db is true
	remove("ptv.db")

	conn = sqlite3.connect("ptv.db")
	cursor = conn.cursor()
	conn.execute('pragma foreign_keys=ON')
	conn.commit()

	# Create tables



	cursor.execute(""" CREATE TABLE IF NOT EXISTS Line (
		_id INTEGER PRIMARY KEY AUTOINCREMENT,
		Name TEXT
	)""")

	# cursor.execute(""" CREATE TABLE IF NOT EXISTS Direction (
	# 	_id INTEGER PRIMARY KEY AUTOINCREMENT,
	# 	LineID TEXT,
	# 	FOREIGN KEY (LineID) REFERENCES Line(_id) ON UPDATE CASCADE
	# )""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS Station (
		_id INTEGER PRIMARY KEY,
		Name TEXT,
		Suburb TEXT,
		Address TEXT,
		Latitude REAL,
		Longitude REAL,
		PTVID INTEGER,
		ZoneID INTEGER,
		Staff TEXT,
		MykiMachines INTEGER,
		MykiChecks INTEGER,
		VlineBookings INTEGER,
		CarParking INTEGER,
		Taxi INTEGER
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS LineStation (
		LineID INTEGER,
		StationID INTEGER,
		FOREIGN KEY (LineID) REFERENCES Line(_id) ON UPDATE CASCADE,
		FOREIGN KEY (StationID) REFERENCES Station(_id) ON UPDATE CASCADE
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS Stop (
		_id INTEGER PRIMARY KEY,
		StationID INTEGER,
		TimeInSeconds INTEGER,
		RunID INTEGER,
		DestinationStationID INTEGER,
		DirectionID REAL,
		Flag Text,
		FOREIGN KEY (StationID) REFERENCES Station(_id) ON UPDATE CASCADE,
		FOREIGN KEY (DestinationStationID) REFERENCES Station(_id) ON UPDATE CASCADE,
		FOREIGN KEY (DirectionID) REFERENCES Direction(_id) ON UPDATE CASCADE
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS DayStop (
		StopID INTEGER,
		Day INTEGER,
		FOREIGN KEY (StopID) REFERENCES Stop(_id) ON UPDATE CASCADE	
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS SpecialDate (
		SpecialDate TEXT,
		Name TEXT
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS Fare (
		_id INTEGER PRIMARY KEY AUTOINCREMENT,
		ZoneID INTEGER,
		FareType INTEGER,
		FareLength INTEGER,
		FareAmount REAL
	)""")

	# Add required android specific tables
	cursor.execute("""CREATE TABLE IF NOT EXISTS"android_metadata" ("locale" TEXT DEFAULT 'en_US')""")
	
	# Wipe any existing static data
	cursor.execute("""DELETE FROM android_metadata""")
	cursor.execute("""DELETE FROM Fare""")

	# Add static data
	cursor.execute("""INSERT INTO "android_metadata" VALUES ('en_US')""")
	fares = [
	(1,1,2,3.58),(2,1,2,2.48),(4,1,2,6.06),
	(1,2,2,1.79),(2,2,2,1.24),(4,2,2,3.03),
	(1,1,24,7.16),(2,1,24,4.96),(4,1,24,12.12),
	(1,2,24,3.58),(2,2,24,2.48),(4,2,24,6.06)
	]
	cursor.executemany("""INSERT INTO Fare VALUES (NULL,?,?,?,?)""", fares)
	conn.commit()

def add_test_data():
	conn = sqlite3.connect("ptv.db")
	cursor = conn.cursor()
	line_data = [
		("Alamein",),
		("Belgrave",),
		("Craigieburn",),
		("Cranbourne",),
		("South Morang",),
		("Frankston",),
		("Glen Waverley",),
		("Hurstbridge",),
		("Lilydale",),
		("Pakenham",),
		("Sandringham",),
		("Stony Point",),
		("Sunbury",),
		("Upfield",),
		("Werribee",),
		("Williamstown",),
		("Showgrounds - Flemington Racecourse",)
	]
	cursor.executemany("""INSERT INTO Line(Name) VALUES (?)""", line_data)
	conn.commit()

	station_data = [
		("Balaclava ","Balaclava","-37.869486","144.993514","19956"),
		("Brighton Beach ","Brighton","-37.926482","144.989157","19950"),
		("Elsternwick ","Elsternwick","-37.884752","145.000902","19954"),
		("Gardenvale ","Brighton","-37.896693","145.004165","19953"),
		("Hampton ","Hampton","-37.937973","145.001466","19949"),
		("Middle Brighton ","Brighton","-37.915135","144.996298","19951"),
		("North Brighton ","Brighton","-37.904883","145.002604","19952"),
		("Prahran ","Prahran","-37.849516","144.98986","19958"),
		("Ripponlea ","Ripponlea","-37.875908","144.995234","19955"),
		("Sandringham ","Sandringham","-37.950328","145.004566","19948"),
		("Windsor ","Windsor","-37.856051","144.992033","19957")
	]
	cursor.executemany("""INSERT INTO Station(Name, Suburb, Latitude, Longitude, PTVID) VALUES (?,?,?,?,?)""", station_data)
	conn.commit()

	linestation_data =[(11,x) for x in range(1,12)]
	cursor.executemany("""INSERT INTO LineStation VALUES (?,?)""", linestation_data)
	conn.commit()		

	


if __name__ == '__main__':
	logging.basicConfig(filename='ptv_log.txt',level=logging.DEBUG)
	prepare_db()
	add_test_data()
	
	# populate_train_lines(TEST_RUN)
	# populate_directions(TEST_RUN)
	# populate_locations(TEST_RUN)
	# populate_stops(TEST_RUN)