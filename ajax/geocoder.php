<?php
/*
 * Hitchwiki Maps
 * Geocoder AJAX file
 * 
 * Examples:
 * - geocoder.php?q=Finland
 * - geocoder.php?q=Tampere,+Finland&service=nominatim
 * - geocoder.php?q=Tampere,+Finland&service=nominatim&debug
 * - geocoder.php?q=64.363,25.332&service=nominatim&mode=reverse
 *
 */ 

header("Cache-Control: no-cache, must-revalidate"); // HTTP/1.1
header("Expires: Sat, 26 Jul 1997 05:00:00 GMT"); // Date in the past
#header("Content-type: application/json");

require_once("../config.php");
require_once("../lib/geocoder.class.php");


/*
 * Initialize
 */ 
$geocoder = new maps_geocode();

// Geocode only on query
if(isset($_GET["q"]) && !empty($_GET["q"])) {

	// Change from geocode(default) to reverse geocode
	if(isset($_GET["mode"]) && $_GET["mode"] == "reverse") $geocoder->set_mode("reverse_geocode");

	// Set service, default is first one from the services list defined in class
	if(isset($_GET["service"]) && !empty($_GET["service"])) $geocoder->set_service($_GET["service"]);
	
	// Set format
	if(isset($_GET["format"]) && !empty($_GET["format"])) $geocoder->set_format($_GET["format"]);

	// Querry
	echo $geocoder->geocode( urlencode(utf8_encode(strip_tags($_GET["q"]))) );
	
}
// If no querry, echo error
else echo $geocoder->geocoder_output(false);





?>