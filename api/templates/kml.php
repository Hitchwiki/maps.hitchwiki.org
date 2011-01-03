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
		
		$return = '<?xml version="1.0" encoding="UTF-8"?>';
		$return .= "\n".'<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:atom="http://www.w3.org/2005/Atom">';
		$return .= "\n".'<Document>';
		$return .= "\n".'<atom:author>';
		$return .= "\n\t".'<atom:name>Hitchwiki '._("Maps").'</atom:name>';
		$return .= "\n".'</atom:author>';
		$return .= "\n".'<atom:link href="'.$settings["base_url"].'" />'."\n";

		$return .= "\n".'<name>'._("Hitchhiking places").'</name>';
		
		return $return;
	}


	// Open or close folder - remember to do both around places
	public function folder($open_or_close='open', $name=false) {

		if($open_or_close == 'open') {
			if($name===false OR empty($name)) $folder_name = _("Hitchhiking places");
			else $folder_name = htmlspecialchars($name);

			$return = "\n<Folder>";
			$return .= "\n<name>".$folder_name."</name>";
			$return .= "\n<open>0</open>";
			//$return .= "\n<description></description>";
			$return .= "\n\n";
		} elseif($open_or_close == 'close') {
			$return = "\n\n</Folder>";
		}
		else $return = '';		
		
		return $return;
	}


	public function footer() {
		
		return "\n\n</Document>\n</kml>";
	}


	public function styles($selected=false) {
		global $settings;

		$hitchability_colors = $settings["hitchability_colors"];

		// Only one style (for a single place)?
		if($selected!==false) {
			$ratings[$selected] = $hitchability_colors[$selected];
		}
		// All colors in use...
		else $ratings = $hitchability_colors;
		
		// Loop out all the styles
		foreach($ratings as $rating => $color) {
			$return .= "\n\n".'<Style id="rating_'.$rating.'">'."\n".
					  '<IconStyle>'."\n".
					    "\t".'<color>ff'.$color.'</color>'."\n".
					    "\t".'<scale>0.5</scale>'."\n".
					  	"\t".'<hotSpot x="0.5" y="0.5" xunits="fraction" yunits="fraction">'."\n".
					    "\t".'<Icon>'."\n".
					    "\t"."\t".'<href>'.$settings["base_url"].'/static/gfx/hh_place_'.$rating.'.png</href>'."\n".
					    "\t".'</Icon>'."\n".
					  '</IconStyle>'."\n".
					'</Style>'."\n\n";
		}

		return $return;
	}


	public function marker($marker=false) {
		if(!empty($marker) OR $marker !== false) {
			global $settings;
			$lang = $settings["default_language"];


			// Open placemark
			$return = "\n".'<Placemark id="'.$marker["id"].'">';
			
			
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


			$return .= "\n".'<visibility>1</visibility>';

			
			// Description
			if(!empty($marker["description"][$lang]["description"])) {
				$return .= "\n".'<description><![CDATA['.bubble_description_html($marker).']]></description>';
			}


			// Coordinates
			$return .= "\n".'<Point>';
			$return .= "\n"."\t".'<coordinates>'.$marker["lon"].','.$marker["lat"].'</coordinates>';
			$return .= "\n".'</Point>';


			// Style
			$return .= "\n".'<styleUrl>#rating_'.$marker["rating"].'</styleUrl>';

			// Close placemark
			$return .= "\n</Placemark>\n";


			return $return;
		
		}
		else return false;
	}

}
?>