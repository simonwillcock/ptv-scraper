from bs4 import BeautifulSoup
from urllib2 import urlopen
import sqlite3
from os import remove

BASE_URL = "http://ptv.vic.gov.au/timetables"
BASE_STOPS_URL = "http://ptv.vic.gov.au/timetables/line/%s"
BASE_TIMETABLE_URL = "http://ptv.vic.gov.au/timetables/linemain/%s"
BASE_LINE_URL = "http://ptv.vic.gov.au/route/view/"
STOP_URL = "http://ptv.vic.gov.au/stop/view/"
STOP_SUBURB_LIST = "http://ptv.vic.gov.au/getting-around/stations-and-stops/metropolitan-trains/"
TEST_RUN = True

def populate_train_lines(test_run=False):
	# Populate train_lines

	html = urlopen(BASE_URL).read()
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

	for line in lines:
		process_line(line,test_run)

def process_line(line,test_run=False):
	# Load Line page to get line url numbers for each direction
	

	# html = urlopen(BASE_LINE_URL+str(line[0])).read()
	# soup = BeautifulSoup(html)
	# list_items = soup.find(id="content").findAll("h3")[0].findNext("ul").findAll("li")
	# for item in list_items:
		# anchor = item.find("a", href=True)
		# direction_id = anchor['href'].replace("timetables/line/","")
		# process_stops(direction_id,line,anchor.getText())



	time_period = "E" # 30 May 2014 until further notice
	day = "T0" # Mon-Fri
	direction_to_city = "R"
	direction_from_city = "H"
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
	(13,"Stony Point","STP"),
	(14,"Sunbury","SYM"),
	(15,"Upfield","UFD"),
	(16,"Werribee","WBE"),
	(17,"Williamstown","WMN"),
	(1482,"Flemington Showgrounds / Flemington Racecourse","AIN"),
	]


	post_data_dictionary = {
	'language':'en', 
	"command":'direct', 
	"net":"vic",
	"project":"ttb",
	"contentFilter":"ALLSTOPS",
	"outputFormat":0,
	"line":"02%S",
	"itdLPxx_selLineDir": direction_from_city,
	"sup":time_period,
	"itdLPxx_selWDType":"T0",
	"actionChoose":"GO"
	}

	print "Processing Stops for %s" % (line[1],)
	html = urlopen(BASE_TIMETABLE_URL % line[0]).read()
	soup = BeautifulSoup(html)
	stop_table = soup.find(id="ttTable")
	
	
def process_stops(direction_id,line,direction_text):
	time_period = "E" # 30 May 2014 until further notice
	day = "T0" # Mon-Fri
	direction_to_city = "R"
	direction_from_city = "H"
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
	(13,"Stony Point","STP"),
	(14,"Sunbury","SYM"),
	(15,"Upfield","UFD"),
	(16,"Werribee","WBE"),
	(17,"Williamstown","WMN"),
	(1482,"Flemington Showgrounds / Flemington Racecourse","AIN"),
	]


	post_data_dictionary = {
	'language':'en', 
	"command":'direct', 
	"net":"vic",
	"project":"ttb",
	"contentFilter":"ALLSTOPS",
	"outputFormat":0,
	"line":"02%S",
	"itdLPxx_selLineDir": direction_from_city,
	"sup":time_period,
	"itdLPxx_selWDType":"T0",
	"actionChoose":"GO"
	}

	print "Processing Stops for %s : %s" % (line[1],direction_text)
	html = urlopen(BASE_STOPS_URL % direction_id).read()
	soup = BeautifulSoup(html)
	stop_table = soup.find(id="ttTable")


def populate_directions(test_run=False):
	# Populate directions
	
	if test_run == False:
		conn = sqlite3.connect("ptv.db")
		cursor = conn.cursor()

		directions = [("City (Flinders Street)",)]
		cursor.execute("""SELECT * FROM train_lines""")
		for row in cursor:
			directions.append((row[1],))
		directions.append(("Flinders Street",))

		# Add to db
		cursor.executemany("""INSERT INTO train_direction VALUES (NULL,?)""", directions)
		conn.commit()
		cursor.execute("""SELECT * FROM train_direction""")
	
def populate_locations(test_run=False):
	# Populate the train_locations table

	html = urlopen(STOP_SUBURB_LIST).read()
	soup = BeautifulSoup(html)

	suburb_list = soup.select("#alpha-list ul li")
	
	for suburb in suburb_list:
		suburb_anchor = suburb.find("a", href=True)
		suburb_name = suburb_anchor.getText()
		print "Processing %s" % suburb_name
		process_suburb(suburb_anchor['href'], suburb_name, test_run)

	conn = sqlite3.connect("ptv.db")
	cursor = conn.cursor()

	print "===============================\nPopulating linelocation table"
	

	line_locations = []
	
	cursor.execute("""DELETE FROM train_linelocation""")

	locations = cursor.execute("""
		SELECT train_locations.location_id, train_locations.lines
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
			SELECT train_lines.line_id
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
		soup = BeautifulSoup(html)
		title = soup.find("h1")
		station_list = title.findNext("ul").findAll("li")

		station_results = []

		for station in station_list:
			station_anchor = station.find("a", href=True)
			station_title = station_anchor.getText()
			station_title_short = station_title.split(" Railway Station", 1)[0]
			print "   Processing station: %s" % station_title_short
			station_results.append(process_station(station_anchor['href'], station_title_short, suburb_name))
		
	
		cursor.executemany("""INSERT INTO train_locations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", station_results)
		conn.commit()

	
		



def process_station(station_link, station_name, suburb_name):
	# Process station and return list of station properties
	html = urlopen(station_link).read()
	soup = BeautifulSoup(html)

	
	location_name = station_name
	suburb = suburb_name
	address = soup.find("h1").findNext("div").find("p").getText().strip()
	coordinates = soup.select("div.aside li")[0].find("a", href=True)["href"].replace("http://maps.google.com/?q=","").split(",")
	stop_id = station_link.replace("http://ptv.vic.gov.au/getting-around/stations-and-stops/view/","")
	zone_id = soup.select("table.stationSummary tr")[2].find("td").getText()
	if zone_id != "1" and zone_id != "2":
		zone_id = 4
	else:
		zone_id = int(zone_id)
	
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

	timetables = soup.select("div.expander")
	lines = [line.getText().replace(" Line","") for line in timetables[0].findAll("a")]
	# linelocations = []
	# for line in lines:
	# 	line_id = cursor.execute("""
	# 	SELECT train_lines.line_id
	# 	FROM train_lines
	# 	WHERE train_lines.line_name = ?
	# 	""",(line,)).fetchone()

	# 	linelocation.append([line_id,])
	lines_string = "/".join(lines)
	
	return [None,location_name, suburb, address, coordinates[0], coordinates[1], stop_id, 
	zone_id, staff, myki_machines, myki_checks, vline_bookings, car_parking, taxi, lines_string]

	# print station_list
	


def prepare_db(rm_db=True):

	if rm_db == True:
		remove("ptv.db")

	conn = sqlite3.connect("ptv.db")

	cursor = conn.cursor()
	

	cursor.execute(""" CREATE TABLE IF NOT EXISTS train_linelocation (
		line_id INTEGER,
		location_id INTEGER,
		FOREIGN KEY (line_id) REFERENCES train_lines(line_id)
		FOREIGN KEY (location_id) REFERENCES train_locations(location_id)
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS train_linedirection (
		linedirection_id INTEGER PRIMARY KEY AUTOINCREMENT,
		line_id INTEGER,
		location_id INTEGER,
		direction_id INTEGER,
		daytype field INTEGER,
		linedirection_line_id INTEGER,
		FOREIGN KEY (line_id) REFERENCES train_lines(line_id)
		FOREIGN KEY (location_id) REFERENCES train_locations(location_id)
		FOREIGN KEY (direction_id) REFERENCES train_direction(direction_id)
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS train_direction (
		direction_id INTEGER,
		direction_name TEXT
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS train_lines (
		line_id INTEGER PRIMARY KEY AUTOINCREMENT,
		line_name TEXT,
		suburbs TEXT
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS train_locations (
		location_id INTEGER PRIMARY KEY,
		location_name TEXT,
		suburb TEXT,
		address TEXT,
		latitude REAL,
		longitude REAL,
		stop_id INTEGER,
		zone_id INTEGER,
		staff TEXT,
		myki_machines INTEGER,
		myki_checks INTEGER,
		vline_bookings INTEGER,
		car_parking INTEGER,
		taxi INTEGER,
		lines TEXT
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS train_stops_monfri (
		line_id INTEGER,
		stop_id INTEGER,
		run_id INTEGER,
		time INTEGER,
		destination INTEGER,
		num_skipped INTEGER,
		direction INTEGER,
		flags INTEGER,
		FOREIGN KEY (line_id) REFERENCES train_lines(line_id),
		FOREIGN KEY (stop_id) REFERENCES train_locations(location_id),
		FOREIGN KEY (destination) REFERENCES train_locations(location_id),
		FOREIGN KEY (direction) REFERENCES train_direction(direction_id)
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS train_stops_sat (
		line_id INTEGER,
		stop_id INTEGER,
		run_id INTEGER,
		time INTEGER,
		destination INTEGER,
		num_skipped INTEGER,
		direction INTEGER,
		flags INTEGER,
		FOREIGN KEY (line_id) REFERENCES train_lines(line_id),
		FOREIGN KEY (stop_id) REFERENCES train_locations(location_id),
		FOREIGN KEY (destination) REFERENCES train_locations(location_id),
		FOREIGN KEY (direction) REFERENCES train_direction(direction_id)
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS train_stops_sun (
		line_id INTEGER,
		stop_id INTEGER,
		run_id INTEGER,
		time INTEGER,
		destination INTEGER,
		num_skipped INTEGER,
		direction INTEGER,
		flags INTEGER,
		FOREIGN KEY (line_id) REFERENCES train_lines(line_id),
		FOREIGN KEY (stop_id) REFERENCES train_locations(location_id),
		FOREIGN KEY (destination) REFERENCES train_locations(location_id),
		FOREIGN KEY (direction) REFERENCES train_direction(direction_id)
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS train_config (
		version_timestamp TEXT,
		db_version TEXT
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS special_dates (
		date TEXT,
		name TEXT
	)""")

	cursor.execute(""" CREATE TABLE IF NOT EXISTS fares (
		fare_id INTEGER PRIMARY KEY AUTOINCREMENT,
		zone_id INTEGER,
		fare_type INTEGER,
		fare_length INTEGER,
		fare_amount REAL
	)""")

	fares = [
	(1,1,2,3.58),(2,1,2,2.48),(4,1,2,6.06),
	(1,2,2,1.79),(2,2,2,1.24),(4,2,2,3.03),
	(1,1,24,7.16),(2,1,24,4.96),(4,1,24,12.12),
	(1,2,24,3.58),(2,2,24,2.48),(4,2,24,6.06)
	]
	cursor.executemany("""INSERT INTO fares VALUES (NULL,?,?,?,?)""", fares)
	conn.commit()

if __name__ == '__main__':
	
	prepare_db(not TEST_RUN)
	populate_train_lines(TEST_RUN)
	populate_directions(TEST_RUN)
	populate_locations(TEST_RUN)
	