<?php
/* Hitchwiki Maps - api/templates/kml.php
 *
 * KML Templates
 * http://code.google.com/apis/kml/documentation/
 * 
 * Load config to set language and stuff
 */
require_once "../config.php";



class template_kml
{

	/*
	 * Construct
	 */
	public function __construct() {

	}

	public function header() {
		global $settings;
		
		$return .= "\n".'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
		$return .= "\n".'<gpx version="1.1" creator="Hitchwiki '._("Maps").' '.$settings["base_url"].
					"\n\t".'xmlns="http://www.topografix.com/GPX/1/1"'.
					"\n\t".'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'.
					"\n\t".'xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd"'.
					">";
		$return .= "\n".'<name>'._("Hitchhiking places").'</name>';

		return $return;
	}


	public function footer() {
		return "\n\n</gpx>";
	}


	public function marker($marker=false) {
		if(!empty($marker) OR $marker !== false) {
			global $settings;
			$lang = $settings["default_language"];

#<wpt lat="45.39260" lon="-121.69937"><ele>2394</ele><name>Barrett Spur</name><sym>Summit</sym></wpt>
/*
  <wpt lat="61.498929" lon="23.750133">
    <ele>0.000000</ele>
    <time>2010-01-10T05:15:06Z</time>
    <name>Auto-Share 001</name>
    <desc>10.1.2010  7:15 am</desc>
  </wpt>
  */

			// Open placemark
			$return = "\n".'<wpt lat="'.$marker["lat"].'" lon="'.$marker["lon"].'">';

			#$return = "\n".'<ele>0.000000</ele>';

			#$return = "\n".'<time>2010-01-10T05:15:06Z</time>';
			
			// Title
			$return .= "\n".'<name>';
			if(!empty($marker["location"])) {
    			$return .= _("a Hitchhiking spot in").' '; 
				
    			// in city, country
    			if(!empty($marker["location"]["locality"])) $return .= $marker["location"]["locality"].', ';
    			//else $return .= $marker["lat"].', '.$marker["lon"].' - ';
				
    			$return .= $marker["location"]["country"]["name"];
    
			} else $return .= _("Hitchhiking spot");
			
			$return .= '</name>';

			
			// Description
			if(!empty($marker["description"][$lang]["description"])) {
				$return .= "\n".'<desc><![CDATA['.bubble_description_html($marker).']]></desc>';
			}

			// Close placemark
			$return .= "\n</wpt>\n";


			return $return;
		
		}
		else return false;
	}

}
?>