<?php
/*
 * Hitchwiki Maps: weather.php
 * Show weather information for lat/lon
 * Uses Wunderground.com API 
 * http://wiki.wunderground.com/index.php/API_-_XML
 */
 
/*
 * Load config to set language and stuff
 */
require_once "../config.php";


if(!isset($_GET["lat"]) OR empty($_GET["lat"]) OR !isset($_GET["lon"]) OR empty($_GET["lon"])) {
	echo '{"error": "true"}';
}
else {

	// Gather data
   $data = readURL("http://api.wunderground.com/auto/wui/geo/WXCurrentObXML/index.xml?query=".urlencode($_GET["lat"]).",".urlencode($_GET["lon"]));
   if(!strstr($data,'<?xml ')) $xml = new SimpleXmlElement('<?xml version="1.0" encoding="UTF-8"?>'.$data, LIBXML_NOCDATA);
   else  $xml = new SimpleXmlElement($data, LIBXML_NOCDATA);
   
   // Print out as JSON
   //$settings["base_url"].'/static/gfx/weather/'.$xml->icons->icon.'.png",
   echo '{
  "observation_location_city": "'.$xml->observation_location->city.'",
  "observation_location_country": "'.$xml->observation_location->country_iso3166.'",
  "observation_location_lat": "'.$xml->observation_location->latitude.'",
  "observation_location_lng": "'.$xml->observation_location->longitude.'",
  "observation_time_rfc822": "'.$xml->observation_time_rfc822.'",
  "observation_time": "'.date("j.n.Y H:i \G\M\T O",strtotime($xml->observation_time_rfc822)).'",
  "weather": {
    "status": "'.$xml->weather.'",
    "icon": "'.$xml->icons->icon_set[9]->icon_url.'",
    "temperature_c": "'.$xml->temp_c.'",
    "temperature_f": "'.$xml->temp_f.'",
    "relative_humidity": "'.$xml->relative_humidity.'",
    "wind_degrees": "'.$xml->wind_degrees.'",
    "wind_mph": "'.$xml->wind_mph.'",
    "pressure_mb": "'.$xml->pressure_mb.'",
    "pressure_in": "'.$xml->pressure_in.'"
   }
}';


}


?>