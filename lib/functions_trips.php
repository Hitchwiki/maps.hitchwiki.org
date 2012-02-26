<?php
/* Hitchwiki - maps
 * Handling location and trips
 * - read_gpx()
 * - user_current_location_link()
 * - user_current_location()
 */


/*
 * Save your location data to SQL
 * Needs an array in format:
 *
    [0] => Array
        (
            [lat] => 20.166139
            [lon] => 99.618021
            [datetime] => 07.20.2011 12:45:21
            [elevation] => 1087
        )

    [1] => Array
        (
            [lat] => 20.166055
            [lon] => 99.617930
            [datetime] => 07.20.2011 12:45:29
            [elevation] => 1087
        )
    ...
    
    At least values "lat", "lon" are required.
 */
function save_location($data, $user_id=false) {
	
    if(!is_id($user_id) OR !is_array($data) OR empty($data)) return false;

    // If received data isn't divided into sub arrays, make it so
    if(count($data) == 1 && !isset($data[0]["lat"])) $data = array(0 => $data);
    
    start_sql();
        $query = "";

        $query .= "INSERT INTO `t_trips_points` (".
                        "`fk_user` ,".
                        "`lat` ,".
                        "`lon` ,".
                        "`end_trip` ,".
                        "`elevation` ,".
                        "`average_elevation` ,".
                        "`accuracy` ,".
                        "`heading` ,".
                        "`speed` ,".
                        "`country` ,".
                        "`continent` ,".
                        "`locality` ,".
                        "`ocean_or_sea` ,".
                        "`datetime` ".
                    ") VALUES ";

        $count = count($data);

        $i=1;
        foreach($data as $location) {

            $last_row = ($count == $i)? true: false;

            // Validate lat & lon
            if(!validate_lat($location["lat"]) OR !validate_lon($location["lon"])) return false;
            
            $elevation = (!isset($location["elevation"]))? "NULL": "'".mysql_real_escape_string($location["elevation"])."'";
            $average_elevation = ($location["average_elevation"]===true)? "1": "NULL";
            $accuracy = (!isset($location["accuracy"]))? "NULL": "'".mysql_real_escape_string($location["accuracy"])."'";
            $heading = (!isset($location["heading"]))? "NULL": "'".mysql_real_escape_string($location["heading"])."'";
            $speed = (!isset($location["speed"]))? "NULL": "'".mysql_real_escape_string($location["speed"])."'";
            $country_code = (!isset($location["country_code"]))? "NULL": "'".mysql_real_escape_string($location["country_code"])."'";
            $continent_code = (!isset($location["continent_code"]))? "NULL": "'".mysql_real_escape_string($location["continent_code"])."'";
            $locality = (!isset($location["locality"]))? "NULL": "'".mysql_real_escape_string($location["locality"])."'";
            $ocean_or_sea = (empty($location["ocean_or_sea"]))? "NULL": "'".mysql_real_escape_string($location["ocean_or_sea"])."'";
            $datetime = (!isset($location["datetime"]))? "NOW()": "'".mysql_real_escape_string($location["datetime"])."'";

            $end_trip = ($last_row)? '1': "NULL";

            $query .= "(".
                        mysql_real_escape_string($user_id).",".
                        "'".mysql_real_escape_string($location["lat"])."',".
                        "'".mysql_real_escape_string($location["lon"])."',".
                        $end_trip.",".
                        $elevation.",".
                        $average_elevation .",".
                        $accuracy.",".
                        $heading.",".
                        $speed.",".
                        $country_code.",".
                        $continent_code.",".
                        $locality.",".
                        $ocean_or_sea.",".
                        $datetime.
                    ")";
            if(!$last_row) $query .= ', ';

            $i++;
        } // foreach

        // Insert created lines to the db
        $res = mysql_query($query);
   	if(!$res) {
            #echo "<pre>\n\n".$query."\n\n</pre>";
            return false;
        } else return true;

}



/*
 * Check database in case of dublicates when adding user's locations
 */
function trips_check_for_dublicates($data, $user_id=false) {

    if(!is_id($user_id) OR !is_array($data) OR empty($data)) return array("error"=>"Invalid data or user ID.");

    // If received data isn't divided into sub arrays, make it so
    if(count($data) == 1 && !isset($data[0]["lat"])) $data = array(0 => $data);

    start_sql();

	$query = "SELECT `lat`,`lon`,`fk_user`,`datetime` FROM `t_trips_points` WHERE `fk_user` = ".mysql_real_escape_string($user_id)." AND `hidden` IS NULL";

	// Build an array
	$res = mysql_query($query);
	if(!$res) return array("error"=>"SQL Error.");

		$locations_in_db = array();
		while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {

		    $locations_in_db[] = $r["lat"].$r["lon"].$r["datetime"];

		}
		
		$return["trapped_places"] = array();
		foreach($data as $place_index => $place) {

			if(in_array($place["lat"].$place["lon"].$place["datetime"], $locations_in_db)) {
				$return["trapped_places"][] = $data[$place_index];
				unset($data[$place_index]);
			}

		}
		
		$return["data"] = array_values($data);
		$return['success'] = true;
		
		return $return;
}




/*
 * Fill location array
 */
function fill_location($data) {

    
    if(is_array($data) && !empty($data)) {

        // Loading geocoder
        require_once("geocoder.class.php");
        $geocoder = new maps_geocode();
        $geocoder->set_mode("reverse_geocode");
        $geocoder->set_format("array");
        
        $filled_data = array();
        
        // If received data isn't divided into sub arrays, make it so
        if(count($data) == 1 && !isset($data[0]["lat"])) $data = array(0 => $data);
        
        // Go through all lines and fill them with additional info if needed

        foreach($data as $line => $location) {
            
            // Previously crawled data
            $filled_data[$line] = $location;
            
            // Geocode some more data for us...
            $geocoded_location = $geocoder->geocoder_output( $geocoder->geocode( urlencode(utf8_encode(strip_tags($location["lat"].",".$location["lon"]))) ) );
            
            
            if(isset($location["elevation"])) {
                    // GPS based elevation was there, assuming it is exact
                    $filled_data[$line]["average_elevation"] = false;
            } else {
                    // Get elevation if it was missing
                    $filled_data[$line]["elevation"] = get_elevation($location["lat"], $location["lon"]);
                    $filled_data[$line]["average_elevation"] = true;
            }
            
            // Go trough geocoded result and fill our previous array with this info if any fields are missing
            $geocoder_properties = array("continent_code","country_code","locality","postcode","address","road","zoom");
            foreach($geocoder_properties as $geocoder_property) {
                if(!isset($location[$geocoder_property]) && isset($geocoded_location[$geocoder_property])) $filled_data[$line][$geocoder_property] = $geocoded_location[$geocoder_property];
            }

            // Get continent if it was missing
            if(!isset($location["continent_code"]) && !empty($filled_data[$line]["country_code"])) $filled_data[$line]["continent_code"] = country_iso_to_continent($filled_data[$line]["country_code"]);
            
            // Add info about sea/ocean on the location
            $filled_data[$line]["ocean_or_sea"] = is_over_water($location["lat"], $location["lon"]);

        }
        
        return $filled_data;
        
    } else return $data;
    
}


function read_csv($data) {
/*
INDEX,RCR,DATE,TIME,VALID,LATITUDE,N/S,LONGITUDE,E/W,HEIGHT,SPEED,HEADING,HDOP,DISTANCE,
1,TD,2011/08/23,04:11:07,SPS,20.077517,N,102.094649,E,150.477 M,12.808 km/h,269.932129,1.94,24611.20 M,
*/

#$lines = explode(")
	return true;
}



function read_gpx($data) {
    
    $xml = new SimpleXmlElement($data);//LIBXML_NOCDATA

    $dateformat = "Y-m-d H:i:s";

	if(strstr($xml["creator"],"glint"))	$source = 3;
	elseif(strstr($xml["creator"],"MotionX")) $source = 4;
	elseif(strstr($xml["creator"],"GPS Stone")) $source = 6;
	
        
	# Glint
	if($source == 3) {
	
		for($i=0; $i < count($xml->trk->trkseg->trkpt); $i++) {
			$return[$i]["lat"] = (string)$xml->trk->trkseg->trkpt[$i]["lat"];
			$return[$i]["lon"] = (string)$xml->trk->trkseg->trkpt[$i]["lon"];
			$return[$i]["datetime"] = date($dateformat, strtotime( (string)$xml->trk->trkseg->trkpt[$i]->time ));
			$ele = round( (string)$xml->trk->trkseg->trkpt[$i]->ele );
			if(!empty($ele)) {
				$return[$i]["elevation"] = $ele;
			}
                        
		}

	}
	elseif($source == 4) {

		$return[0]["lat"] = (string)$xml->wpt["lat"];
		$return[0]["lon"] = (string)$xml->wpt["lon"];
		$return[0]["name"] = (string)$xml->wpt->name;
		$return[0]["datetime"] = date($dateformat, strtotime( (string)$xml->wpt->time ));
		$return[0]["description"] = (string)$xml->wpt->desc;
		
		$ele = round( (string)$xml->wpt->ele );
		if(!empty($ele)) {
			$return[0]["elevation"] = $ele;
		}
			
	
	}
	elseif($source == 6) {
	
		for($i=0; $i < count($xml->trk->trkseg->trkpt); $i++) {
			$return[$i]["lat"] = (string)$xml->trk->trkseg->trkpt[$i]["lat"];
			$return[$i]["lon"] = (string)$xml->trk->trkseg->trkpt[$i]["lon"];
			$return[$i]["hdop"] = (string)$xml->trk->trkseg->trkpt[$i]->hdop;
			$return[$i]["vdop"] = (string)$xml->trk->trkseg->trkpt[$i]->vdop;
			$return[$i]["datetime"] = date($dateformat, strtotime( (string)$xml->trk->trkseg->trkpt[$i]->time ));
			
			$ele = round( (string)$xml->trk->trkseg->trkpt[$i]->ele );
			if(!empty($ele)) {
				$return[$i]["elevation"] = $ele;
			}
		}
	
	}
	
	
    #$return["raw"] = $xml;

    return $return;
}



/*
 * Gives an elevation in meters
 *
 * http://www.geonames.org/export/web-services.html
 * Elevation - Aster Global Digital Elevation Model
 * sample area: ca 30m x 30m, between 83N and 65S latitude. Result : a single number giving the elevation in meters 
 * according to aster gdem, ocean areas have been masked as "no data" and have been assigned a value of -9999"
 */
function get_elevation($lat,$lon) {

        // Validate lat & lon
        if(!validate_lat($lat) OR !validate_lon($lon)) return false;

	$elevation = readURL("http://ws.geonames.org/astergdem?lat=".urlencode($lat)."&lng=".urlencode($lon));

	if(trim($elevation) == '-9999') return '0';
	elseif(!empty($elevation)) return trim($elevation);
	else return false;
}

/*
 * Tells if location is in sea/ocean (In English) and returns the name of it. Over land returns false.
 */
function is_over_water($lat,$lon) {

        // Validate lat & lon
        if(!validate_lat($lat) OR !validate_lon($lon)) return false;
        
	$data = readURL("http://ws.geonames.org/ocean?lat=".$lat."&lng=".$lon);
	
	/* No will return:
		<?xml version="1.0" encoding="UTF-8" standalone="no"?>
		<geonames>
		<status message="we are afraid we could not find an ocean for latitude and longitude :60.943095,24.891561" value="15"/>
		</geonames>
		
	* Yes will return:
		<?xml version="1.0" encoding="UTF-8" standalone="no"?>
		<geonames>
		<ocean>
		<name>Gulf Of Finland</name>
		</ocean>
		</geonames>
	*/
	
	// Lue XML tauluun
	$xml = new SimpleXmlElement($data, LIBXML_NOCDATA);
	
	$name = $xml->geonames->ocean->name;
	
	if(!empty($name)) return $name;
	else return false;
}

/*
 * Produce a link and text of user's current location (eg. "Bangkok, Thailand")
 */
function user_current_location_link($user_id=false, $show_when=true) {
	$location = user_current_location($user_id, true);

	if(isset($location["error"])) return false;
	else {
		$random_id = time().rand(100,999);
        
		$return = '<a href="./trip.php?user_id='.$user_id.'" title="'._("Show on the map").'" class="location_link" id="location_link-'.$random_id.'">';
                
                if(!empty($location["location"]["city"])) $return .= $location["location"]["city"];
                
                if(!empty($location["location"]["city"]) && !empty($location["location"]["country"]["name"])) $return .= ', ';
                
                if(!empty($location["location"]["country"]["name"])) $return .= $location["location"]["country"]["name"];
                
                $return .= '</a>';
                
                $return .= '<script type="text/javascript">
                            $(document).ready(function() {
                                $("a#location_link-'.$random_id.'").click(function(e){
                                   e.preventDefault();
                                   $(this).blur();
                                   go_to_current_location();
                                });
                            }); </script>';
                
                if($show_when) {
                    $return .= ' <span class="when" title="'.date(DATE_RFC822,strtotime($location["datetime"])).'">'.relative_date($location["datetime"]).'</span>';
                }
                
                return $return;
	}
}

/* User's current location
 * Return an array of users (by id or current logged in user) current location
 * Returns false if user has hidden location, user-id not found or user doesn't have any location info
 * $user_id int/false
 * $more true/false (returns more detailed location info if true. Otherwice just id and lat/lon -info. default: false)
 */
function user_current_location($user_id=false, $more=false) {
	global $settings;

	if($user_id === false) $user = current_user(); // Get current logged in user's info if no id given
	elseif(is_id($user_id)) $user = user_info($user_id); // Get user's info for given ID
	else return array("error"=>"No user ID given and no user logged in right now."); // We really need user ID for this stuff...

	// For checking private location permissions, we might need to get current logged in user - but not always!
	if($user["private_location"] <= 2 && $user_id === false) $logged_user = $user; // Current user is already stored in $user
	elseif($user["private_location"] <= 2) $logged_user = current_user();

	// Check for user's privacy permissions
	if($user === false) return array("error"=>"User not found.");
	elseif($user["private_location"] <= 2 && $logged_user === false) return array("private_location" => true, "error"=>"User's location is private.");
	elseif($user["private_location"] == 1 && $user["id"] != $logged_user["id"]) return array("private_location" => true, "error"=>"User's location is private.");
	else {

		start_sql();

		$query = "SELECT * FROM `t_trips_points` WHERE `fk_user` = ".mysql_real_escape_string($user["id"])." AND `hidden` IS NULL ORDER BY `datetime` DESC LIMIT 1";

		// Build an array
   		$res = mysql_query($query);
   		if(!$res) return array("error"=>"SQL Error.");

		while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {

		    $result["id"] = $r["id"];
   		    $result["trip_id"] = $r["fk_trip"];
   		    $result["lat"] = $r["lat"];
   		    $result["lon"] = $r["lon"];
		    
		    if($more) {
	   		    $result["elevation"] = $r["elevation"];
	   		    $result["accuracy"] = $r["accuracy"];
	   		    $result["heading"] = $r["heading"];
	   		    $result["speed"] = $r["speed"];

			    $result["location"]["city"] = $r["locality"];
			    $result["location"]["country"]["iso"] = $r["country"];
			    $result["location"]["country"]["name"] = ISO_to_country($r["country"]);
			    $result["location"]["continent"]["code"] = $r["continent"];
			    $result["location"]["continent"]["name"] = continent_name($r["continent"]);
	
			    $result["user"]["id"] = $r["fk_user"]; 
			    $result["user"]["name"] = username($r["fk_user"]);

			    $result["link"] = $settings["base_url"]."/?trip_place=".$r["id"];
			    $result["datetime"] = $r["datetime"];
		    }
		    return $result;
   		}

	// No user found or user had hidden location
	} #else return false;
}


?>