<?php
/* Hitchwiki - maps
 * Validating / manipulating stings and codes functions
 * - country_to_ISO()
 * - ISO_to_country()
 * - shortlang()
 * - langcode()
 * - continent_name()
 * - country_iso_to_continent()
 * - validate_lat()
 * - validate_lon()
 * - is_id()
 * - hitchability2textual()
 * - hitchability2numeric()
 * - nicetime()
 * - relative_date()
 * - protect_email()
 * - is_valid_email_address()
 */




/* 
 * Shorten country names to ISO 3166-codes
 * Finland -> FI, Germany -> DE, etc
 * Todo: all languages -search
 */
function country_to_ISO($country="",$db=false, $lang="") {
	global $settings;
	
	$country = trim($country);
		
	if(!empty($country)) {

		// Search from a ready made database
		if(is_array($db) && !empty($db)) {
		
			if(isset($db[strtolower($country)])) return $db[strtolower($country)];
			else return false;
		
		// Check from sql-db
		} else {
		
			// Gather data
			start_sql();
			
			$query = "SELECT iso FROM `t_countries` WHERE ";
			
			foreach($settings["valid_languages"] as $code => $lang) {
				if($code != $settings["default_language"]) $query .= "LOWER(".$code.") = LOWER('".mysql_real_escape_string($country)."') OR ";
			}
			// By lefting default language out from foreach loop, we can add it now Without "OR" at the end 
			$query .= "LOWER(".$settings["default_language"].") = LOWER('".mysql_real_escape_string($country)."') LIMIT 1";
			
			
			$result = mysql_query($query);
			if (!$result) {
	   			die("query failed.");
			}
			
			// Result
			if(mysql_num_rows($result) > 0) {
				while($row = mysql_fetch_array($result, MYSQL_ASSOC)) {
				    return $row["iso"];
				}
			}
			else return false;
			
		}
	// Nothing to look for
	} else return false;
}



/* 
 * Give names behind ISO-country codes
 * FI -> Finland, DE -> Germany, etc
 */
function ISO_to_country($iso, $db=false, $lang="") {

	if(!empty($iso)) {

		global $settings;
		
		// Check if language is valid (if not, use default)
		// Settings comes from config.php
		if(empty($settings["valid_languages"][$lang])) $lang = $settings["language"];


		if(is_array($db) && !empty($db)) {
		
			return $db[$iso];
		
		} else {
		
			// Gather data
			start_sql();
			$result = mysql_query("SELECT `iso`,`".mysql_real_escape_string($lang)."` FROM `t_countries` WHERE iso = '".mysql_real_escape_string(strtoupper($iso))."' LIMIT 1");
			if (!$result) {
	   			return false;
			}
			
			// Result
			if(mysql_num_rows($result) > 0) {
				while($row = mysql_fetch_array($result, MYSQL_ASSOC)) {
				    return $row[$lang];
				}
			}
			else return $iso;
		}
	} else return false;
}



/* 
 * Shorten longer language codes
 * ISO_639-1 ('en_UK' => 'en')
 *
 * mode: country / language
 */
function shortlang($lang="", $mode="language") {

	// Use current in use -language if not specified
	if(empty($lang)) {
		global $settings;
		$lang = $settings["language"];
	}
	
	// Do the shortie!
	if(strstr($lang, "_")) $bits = explode("_", $lang);
	elseif(strstr($lang, "@")) $bits = explode("@", $lang);
	else {
		$bits[0] = substr($lang, 0, 2);
		$bits[1] = "world";
	}
	
	// Give 'em that shortie...
	if($mode=="language") return $bits[0];
	elseif($mode=="country") return $bits[1];
}


/*
 * Format language for xml:lang and html:lang
 */
function langcode($lang=false) {
	if($lang==false) {
		global $settings;
		$lang = $settings["language"];
	}
	$lang = str_replace('_','-',$lang);
	$lang = str_replace('@','-',$lang);
	return $lang;
}


/*
 * Returns the reading direction of the current selected language
 * 
 * ltr = left to right
 * rtl = right to left
 * 
 * Define a list of rtl languages in config.php, by default languages are considered being ltr.
 */
function langdir() {
	global $settings;

	if(isset($settings["language"]) && in_array($settings["language"], $settings["rtl_languages"])) return "rtl";
	else return "ltr";
}


/* 
 * Content name
 * NA => North America
 */
function continent_name($code="") {

	$continent = list_continents();
	
	if(!empty($code)) return $continent[$code]["name"];
	else return $code;
}


/* 
 * In which continent this country is in?
 * Returns a short code against country ISO code
 * FI => EU
 */
function country_iso_to_continent($code="") {

	if(!empty($code) && strlen($code) == 2) {
		start_sql();
		
		// Get a continetn code from database
		$res = mysql_query("SELECT `iso`,`continent` FROM `t_countries` WHERE `iso` = '".mysql_real_escape_string(strtoupper($code))."' LIMIT 1");
		if(!$res) return false;
		
		// If we have a result, go and get the name
		if(mysql_num_rows($res) > 0) {
		    while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
		    	return $r["continent"];
		    }
		}
	}
}


/*
 * Validate Latitude
 * Check that latitude is above -90 and below 90
 * return true/false
 */
function validate_lat($lat) {
	if($lat !== false && $lat > -90 && $lat < 90) return true;
	else return false;
}


/*
 * Validate Longitude
 * Check that longitude is above -180 and below 180
 * return true/false
 */
function validate_lon($lon) {
	if($lon !== false && $lon > -180 && $lon < 180) return true;
	else return false;
}


/*
 * Validate ID
 * return true/false
 */
function is_id($id) {
	if($id !== false && $id >= 0) return true;
	else return false;
}


/* 
 * Return a textual hitchability
 */
function hitchability2textual($rating=false) {

	if($rating == 1) return _("Very good");
	elseif($rating == 2) return _("Good");
	elseif($rating == 3) return _("Average");
	elseif($rating == 4) return _("Bad");
	elseif($rating == 5) return _("Senseless");
	else return _("Unknown");
}


/* 
 * Return a numerical hitchability
 * Because how ratings are saved to the database, they might be understood wrong when showing in "stars" mode
 */
function hitchability2numeric($rating=false) {
	
	if($rating==false) return "0/5";
	else {
		if(strlen($rating) > 3) $rating = round($rating, 1);
	/*
		1 = 5
		2 = 4
		3 = 3
		4 = 2
		5 = 1
	*/
		return (6-$rating)."/5";
	}	
}


/*
 * Return time in nice hours/minutes -format
 * TODO
 */
function nicetime($minutes) {


	if(!is_numeric($minutes) OR $minutes < 0) return _("Unknown");
	elseif($minutes < 60) return $minutes._("min");
	else {
		$hours = floor($minutes/60);
		$return = $hours._("h");
		
		$leftover = $minutes-($hours*60);
		
		if($leftover != 0) $return .= " ".$leftover._("min");
		
		return $return;
	}
}



/*
* Smarty plugin
* -------------------------------------------------------------
* Type:     modifier
* Name:     relative_date
* Version:  1.1
* Date:     November 28, 2008
* Author:   Chris Wheeler <chris@haydendigital.com>
* Purpose:  Output dates relative to the current time
* Input:    timestamp = UNIX timestamp or a date which can be converted by strtotime()
*           days = use date only and ignore the time
*           format = (optional) a php date format (for dates over 1 year)
* -------------------------------------------------------------
*/
function relative_date ($timestamp, $days = false, $format = "j.n.Y")
{
    if (!is_numeric($timestamp)) {
        // It's not a time stamp, so try to convert it...
        $timestamp = strtotime($timestamp);
    }

    if (!is_numeric($timestamp)) {
        // If its still not numeric, the format is not valid
        return false;
    }

    // Calculate the difference in seconds
    $difference = time() - $timestamp;

    // Check if we only want to calculate based on the day
    if ($days && $difference < (60*60*24)) {
        return _("Today");
    }
    if ($difference < 3) {
        return _("Just now");
    }
    if ($difference < 60) {
        return sprintf(_("%d seconds ago"), $difference);
    }
    if ($difference < (60*2)) {
          return sprintf(ngettext("%d minute ago", "%d minutes ago", 1, 1));
    }
    if ($difference < (60*60)) {
    	  $time = intval($difference / 60);
          return sprintf(ngettext("%d minute ago", "%d minutes ago", $time, $time));
    }
    if ($difference < (60*60*2)) {
          return sprintf(ngettext("%d hour ago", "%d hours ago", 1, 1));
    }
    if ($difference < (60*60*24)) {        
    	  $time = intval($difference / (60*60));
          return sprintf(ngettext("%d hour ago", "%d hours ago", $time, $time));
    }
    if ($difference < (60*60*24*2)) {
          return sprintf(ngettext("%d day ago", "%d days ago", 1, 1));
    }
    if ($difference < (60*60*24*7)) {
    	  $time =  intval($difference / (60*60*24));
          return sprintf(ngettext("%d day ago", "%d days ago", $time, $time));
    }
    if ($difference < (60*60*24*7*2)) {
          return sprintf(ngettext("%d week ago", "%d weeks ago", 1, 1));
    }
    if ($difference < (60*60*24*7*(52/12))) {
    	  $time = intval($difference / (60*60*24*7));
          return sprintf(ngettext("%d week ago", "%d weeks ago", $time, $time));
    }
    if ($difference < (60*60*24*7*(52/12)*2)) {
          return sprintf(ngettext("%d month ago", "%d months ago", 1, 1));
    }
    if ($difference < (60*60*24*364)) {
    	  $time = intval($difference / (60*60*24*7*(52/12)));
          return sprintf(ngettext("%d month ago", "%d months ago", $time, $time));
    }


    // More than a year ago, just return the formatted date
    return @date($format, $timestamp);

}



/* 
 * Protect email against spam
 */
function protect_email($email) {
	return str_replace("@", "&#64;", $email);
}


/*
 * Validate en email
 *
 * an RFC822 compliant email address matcher
 * Originally written by Cal Henderson: 
 * http://www.iamcal.com/publish/articles/php/parsing_email/
 */
function is_valid_email_address($email){

    $qtext = '[^\\x0d\\x22\\x5c\\x80-\\xff]';

    $dtext = '[^\\x0d\\x5b-\\x5d\\x80-\\xff]';

    $atom = '[^\\x00-\\x20\\x22\\x28\\x29\\x2c\\x2e\\x3a-\\x3c'.
    	'\\x3e\\x40\\x5b-\\x5d\\x7f-\\xff]+';

    $quoted_pair = '\\x5c[\\x00-\\x7f]';

    $domain_literal = "\\x5b($dtext|$quoted_pair)*\\x5d";

    $quoted_string = "\\x22($qtext|$quoted_pair)*\\x22";

    $domain_ref = $atom;

    $sub_domain = "($domain_ref|$domain_literal)";

    $word = "($atom|$quoted_string)";

    $domain = "$sub_domain(\\x2e$sub_domain)*";

    $local_part = "$word(\\x2e$word)*";

    $addr_spec = "$local_part\\x40$domain";

    return preg_match("!^$addr_spec$!", $email) ? true : false;
}



?>