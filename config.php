<?php
/*
 * Hitchwiki Maps: config.php
 *
 */

/* 
 * SETTINGS you might want to adjust:
 */
// Tools for devs:
$settings["debug"] = 					false;
$settings["maintenance_page"] = 		false; // Set true to close down visible page
$settings["maintenance_api"] = 			false; // Set true to close down API
$settings["non_maintenance_ip"] = 		array('78.56.243.106'); // Add IP addresses to whom show a normal page while in maintenance mode.
	
$settings["google_maps_api_key"] = 		"ABQIAAAAYDTWHOdWKYoKDX_oeVBxuhRObnF2ChZr0G6vmgKt7y3TIJm9KRRFWoNg1XGbB_ySGAVnc2-CYpGqrQ"; // API key to enable
$settings["yahoo_maps_appid"] = 		""; // APP ID to enable
$settings["ms_virtualearth"] = 			false; // false|true to enable

$settings["google_analytics_id"] =		""; // ID to enable

// fb:admins or fb:app_id - A comma-separated list of either the Facebook IDs of page administrators or a Facebook Platform application ID. At a minimum, include only your own Facebook ID.
$settings["fb"]["admins"] = 			"133644853341506";
$settings["fb"]["page_id"] = 			"133644853341506";

$settings["fb"]["app"]["id"] = 			"139879862696959";
$settings["fb"]["app"]["api"] = 		"f25317793df03253a12d4219b0d9bfdd";
$settings["fb"]["app"]["secret"] = 		"68c4828ccd98910f750e55514c3e2f20";

$settings["email"] = 					"maps@hitchwiki.org";
$settings["cookie_prefix"] = 			"hitchwiki_maps_";

// Languages
// See ./admin/ to set up new languages
$settings["default_language"] = 		"en_UK"; // Fall back and default language
$settings["valid_languages"] = 			array( // Remember to add language cells to your database too!
		"en_UK" => "English",
		"es_ES" => "Español",
		"fi_FI" => "Suomi",  
		"de_DE" => "Deutsch", 
		"nl_NL" => "Nederlands",
		"pt_PT" => "Português",
		"ru_RU" => "Русский",
		"ro_RO" => "Română",
		"sv_SE" => "Svenska",
		"pl_PL" => "Polski",
		"lt_LT" => "Lietuvių",
		"lv_LV" => "Latviešu",
		"fr_FR" => "Français",
		"it_IT" => "Italiano",
		"zh_CN" => "中文"
);

$settings["languages_in_english"] = 	array(
		"en_UK" => "English", 
		"es_ES" => "Spanish", 
		"fi_FI" => "Finnish", 
		"de_DE" => "German", 
		"nl_NL" => "Dutch",
		"pt_PT" => "Portuguese", 
		"ru_RU" => "Russian", 
		"ro_RO" => "Romanian",
		"sv_SE" => "Swedish",
		"pl_PL" => "Polish",
		"lt_LT" => "Lithuanian",
		"lv_LV" => "Latvian",
		"fr_FR" => "French",
		"it_IT" => "Italian",
		"zh_CN" => "Chinese"
); 

// Usually you don't need to edit this, but you can set it manually, too. No ending "/".
$settings["base_url"] = "http://hitchwiki.org/maps";
#TODO, automate this. "http" . ((!empty($_SERVER['HTTPS'])) ? "s" : "") . "://".$_SERVER['SERVER_NAME'].dirname($_SERVER['REQUEST_URI']);

/*
 * MySQL settings
 */
$mysql_conf = array(
	"user"		=> 		'hitchwiki', 
	"password"	=> 		'R5nxtY5SQS8zKQLS',
	"host"		=> 		'localhost',
	"database"	=> 		'hitchwiki_maps',
	"mediawiki_db" => 	'pg_hitchwiki_en' // the DB where Maps will look for the users info, eg. email
);



/**** DO NOT EDIT FROM HERE ****/

session_name('pg_hitchwiki_en_session');
session_start();

/*
 * Select language (sets $settings["language"])
 * Load common functions
 * Load Maps API
 * Load Markdown
 */
require_once "lib/language.php";
require_once "lib/functions.php";
require_once("lib/api.php");
require_once "lib/markdown.php";


/*
 * Map layer translated names
 * You cannot add/remove used layers from here, but you need also edit static/js/main.js
 */
$map_layers = array(
    "osm" => array(
    		"mapnik" => "Open Street map",
    		"osmarender" => "Open Street map - Tiles@Home"
    ),
    "google" => array(
    		"gsat" => "Google "._("Satellite"),
    		"ghyb" => "Google "._("Hybrid"),
    		"gmap" => "Google "._("Streets"),
    		"gphy" => "Google "._("Physical")
    ),
    "yahoo" => array(
    		"yahoohyb" => "Yahoo "._("Hybrid"),
    		"yahoosat" => "Yahoo "._("Satellite"),
    		"yahoo" => "Yahoo "._("Street")
    ),
    "vearth" => array(
    		"vehyb" => "Virtual Earth "._("Hybrid"),
    		"veaer" => "Virtual Earth "._("Aerial"),
    		"veroad" => "Virtual Earth "._("Roads")
    )
);

?>
