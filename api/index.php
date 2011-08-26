<?php
/* Hitchwiki Maps - API
 *
 * Requires:
 * lib/api.php
 * lib/functions.php
 *
 */
 

/*
 * Init
 */
if(@is_file('../config.php')) require_once "../config.php";
else $settings["maintenance_api"] = true;


/*
 * Put up a maintenance -sign
 */
if($settings["maintenance_api"]===true && !in_array($_SERVER['REMOTE_ADDR'], $settings["non_maintenance_ip"])) {

	if(isset($_GET["ping"])) echo '{"ping":"maintenance"}';
	else echo '{"error":"true","error_description":"maintenance"}';

	exit;
}


$api = new maps_api("json");


/*
 * Set output format (default output is json, kml available)
 */
if(isset($_GET["format"])) $api->set_format($_GET["format"]);

/*
 * Set respond in JSONP format if requested
 * http://en.wikipedia.org/wiki/JSONP
 */
if(isset($_GET["jsonp"])) $api->jsonp($_GET["jsonp"]);
elseif(isset($_GET["callback"])) $api->jsonp($_GET["callback"]);

 
/*
 * Set some headers
 */
header("Cache-Control: no-cache, must-revalidate"); // HTTP/1.1
header("Expires: Sat, 26 Jul 1997 05:00:00 GMT"); // Date in the past
#header('Content-Encoding: gzip'); 

// Force to download as a file
if(isset($_GET["download"])) {
	
	// Set header depending on format
	if($api->format == "json") {
		header('Content-type: application/json; charset=utf8');
		$file_format = "json";
	}
	elseif($api->format == "kml") {
		header('Content-type: application/vnd.google-earth.kml+xml; charset=utf8');
		$file_format = "kml";
	}
	elseif($api->format == "kmz") {
		header('Content-type: application/vnd.google-earth.kmz; charset=utf8');
		$file_format = "kmz";
	}
	elseif($api->format == "gpx") {
		header('Content-type: application/gpx+xml; charset=utf8');
		$file_format = "kml";
	}
	else {
		header('Content-type: text/plain; charset=utf8');
		$file_format = "txt";
	}
	
	// Set a filename
	if($_GET["download"] != "" && strlen($_GET["download"]) <= 255 && preg_match ("/^([a-zA-Z0-9._-]+)$/", $_GET["download"])) $filename = $_GET["download"];
	else $filename = "places";
	
	// Send it to the browser
	header('Content-Disposition: attachment; filename="'.$filename.'.'.$file_format.'"');
}
elseif($api->format == "kml") {
	header('Content-type: application/vnd.google-earth.kml+xml; charset=utf8');
}
// Just serve as a text stream if format is "string" (to make it easier to read)
elseif($api->format == "string") {
	header('Content-type: text/plain; charset=utf8');
}


/*
 * Get markers from a square area by coordinates
 * Square corners, eg. 60.0066276,60.3266276,24.783508,25.103508 (Helsinki, Finland)
 */
elseif(isset($_GET["bounds"]) && !empty($_GET["bounds"])) {

	// Get bounds from query
	$bounds = explode(",", $_GET["bounds"]);
	
	// Get description with markers?
	if(isset($_GET["description"]) && isset($settings["valid_languages"][$_GET["description"]])) $description = $_GET["description"];
	else $description = false;
	
	// Validate query
	if(count($bounds) != 4 OR !is_numeric($bounds[0]) OR !is_numeric($bounds[1]) OR !is_numeric($bounds[2]) OR !is_numeric($bounds[3])) $api->API_error("Invalid query!");

	// Get markers only for trips
	if(isset($_GET["trips"]) && isset($_GET["lines"])) {
		if(isset($_GET["user_id"])) echo $api->getTripLinesByBound($_GET["user_id"], $bounds[0],$bounds[1],$bounds[2],$bounds[3]);
		else echo $api->API_error("Missing user ID!");
	}
	// Get markers only for trips
	elseif(isset($_GET["trips"])) {
		if(isset($_GET["user_id"])) echo $api->getTripsByBound($_GET["user_id"], $bounds[0],$bounds[1],$bounds[2],$bounds[3]);
		else echo $api->API_error("Missing user ID!");
	}
	// Get markers normally for hitchhiking places
	else echo $api->getMarkersByBound($bounds[0],$bounds[1],$bounds[2],$bounds[3]);
	
}


/*
 * Get markers from a city
 */
if(isset($_GET["locality"]) && !empty($_GET["locality"])) {

	// Get by city/town eg. "Helsinki" (no need to add country to it)
	echo $api->getMarkersByLocality($_GET["locality"]);

}



/*
 * Get marker by ID
 */
if(isset($_GET["place"]) && !empty($_GET["place"])) {

	if(isset($_GET["dot"])) echo $api->getMarker($_GET["place"]); // Get just a dot
	else echo $api->getMarker($_GET["place"], true); // Get all info

}



/*
 * Get markers from a country
 */
if(isset($_GET["country"]) && !empty($_GET["country"])) {

	// Get by country ISO-code, eg. "FI"
	echo $api->getMarkersByCountry($_GET["country"]);

}


/*
 * Get markers from a continent
 */
if(isset($_GET["continent"]) && !empty($_GET["continent"])) {

	// Get by continent short code:
	/*
	AS = Asia
	AF = Africa
	NA = North America
	SA = South America
	AN = Antarctica
	EU = Europe
	OC = Australia and Oceania
	*/
	
	echo $api->getMarkersByContinent($_GET["continent"]);

}


/*
 * Get a list of continents
 */
if(isset($_GET["continents"])) {

	echo $api->getContinents();

}


/*
 * Get a list of countries
 */
if(isset($_GET["countries"])) {

	// List with coordinates?	
	$coordinates = (isset($_GET["coordinates"])) ? true: false;
	
	
	// List stuff out
	if($_GET["countries"]=="all") echo $api->getCountries(true, $coordinates); // List all countries
	else echo $api->getCountries(false, $coordinates); // List only countries with places

}



/*
 * Get a list of countries
 */
if(isset($_GET["country_info"])) {

	if(isset($_GET["lang"])) echo $api->getCountry($_GET["country_info"], $_GET["lang"]);
	else echo $api->getCountry($_GET["country_info"]);

}


/*
 * Get all markers from the DB
 */
if(isset($_GET["all"])) {

	echo $api->getAll();

}


/*
 * Get comments
 */
if(isset($_GET["comments"])) {

	// With limit?
	$limit = (isset($_GET["limit"]) && preg_match ("/^([0-9,]+)$/", $_GET["limit"])) ? $_GET["limit"]: false;

	// By ID or all?
	if(empty($_GET["comments"])) echo $api->getComments(false, $limit);
	else echo $api->getComments($_GET["comments"], $limit);

}


/*
 * Add comment
 */
if(isset($_GET["add_comment"])) {

	if(!empty($_POST)) echo $api->addComment($_POST);
	else echo $api->API_error("Send comment by POST-method.");

}


/*
 * Update/add description
 */
if(isset($_GET["add_description"])) {

	if(!empty($_POST)) echo $api->addDescription($_POST);
	else echo $api->API_error("Send description by POST-method.");

}



/*
 * Remove comment
 */
if(isset($_GET["remove_comment"])) {

	echo $api->removeComment($_GET["remove_comment"]);

}


/*
 * Remove rating
 * by ID of the rating (rating_id) or by id of the place (place_id)
 */
if(isset($_GET["remove_rating"])) {

	if(isset($_GET["rating_id"])) echo $api->removeRating($_GET["rating_id"], false);
	elseif(isset($_GET["place_id"])) echo $api->removeRating(false, $_GET["place_id"]);
	else echo $api->API_error("No ID defined.");

}

/*
 * Remove waitingtime
 */
if(isset($_GET["remove_waitingtime"])) {

	echo $api->removeWaitingtime($_GET["remove_waitingtime"]);

}


/*
 * Add place
 */
if(isset($_GET["add_place"])) {

	if(!empty($_POST)) echo $api->addPlace($_POST);
	else echo $api->API_error("Send place by POST-method.");

}


/*
 * Give a waitingtime for a place
 */
if(isset($_GET["add_waitingtime"]) && isset($_GET["place_id"])) {

	if(isset($_GET["user_id"])) echo $api->addWaitingtime($_GET["add_waitingtime"], $_GET["place_id"], $_GET["user_id"]);
	else echo $api->addWaitingtime($_GET["add_waitingtime"], $_GET["place_id"]);

}


/*
 * Rate place
 */
if(isset($_GET["rate"]) && isset($_GET["place_id"])) {

	if(isset($_GET["user_id"])) echo $api->rate($_GET["rate"], $_GET["place_id"], $_GET["user_id"]);
	else echo $api->rate($_GET["rate"], $_GET["place_id"]);

}



/*
 * Get waitingtime for a place
 */
if(isset($_GET["waitingtime"])) {

	echo $api->waitingtime($_GET["waitingtime"]);

}



/*
 * Delete user profile
 */
if(isset($_GET["delete_profile"])) {

	echo $api->deleteProfile($_GET["delete_profile"]);

}



/*
 * Get a list of available languages
 */
if(isset($_GET["languages"])) {

	echo $api->getLanguages();

}


/* 
 * Add public transport page to the catalog
 */
if(isset($_GET["add_public_transport"])) {

	echo $api->AddPublicTransport($_POST);

}


// Return "pong"
if(isset($_GET["ping"])) echo $api->output(array("ping"=>"pong"));#echo '{"ping":"pong"}';

// forward to the infopage if nothing was requested
if(empty($_GET) && empty($_POST)) echo $api->API_error(); //header("Location: ../?page=api");


?>