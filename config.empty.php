<?php
/*
 * Hitchwiki Maps: config.empty.php
 *
 * Copy this file to "config.php"
 */

/* 
 * SETTINGS you might want to adjust:
 */
 
$settings["cache_buster"] = 			''; // Force user's browser to refresh JS and CSS files by changing this to something new
$settings["debug"] = 					true;
$settings["allow_admins"] = 			true; // Set false to temporarily take off all admin priviliges
$settings["maintenance_page"] = 		false; // Set true to close down visible page
$settings["maintenance_api"] = 			false; // Set true to close down API
$settings["non_maintenance_ip"] = 		array(); // Add IP addresses to whom show a normal page while in maintenance mode.

// General settings
$settings["email"] = 					"";
$settings["cookie_prefix"] = 			"hitchwiki_maps_";
$settings["hitchability_colors"] = 		array('ffffff','00ad00','96ad00','ffff00','ff8d00','ff0000'); // Rating => hex color without # (0-5)

// Services
$settings["google"]["api"]["maps_key"] = 	""; // API key to enable
$settings["yahoo"]["maps_appid"] = 			""; // APP ID to enable
$settings["ms"]["virtualearth"] = 			false; // false|true to enable
$settings["geonames"]["user"] = 			""; // User account for geonames.org
$settings["geonames"]["email"] = 			""; // Email for geonames.org

// OAuth 2 Credentials for Google Latitude API
$settings["google"]["api"]["client_id"] =         "";
$settings["google"]["api"]["client_secret"] =     "";
$settings["google"]["api"]["api_key"] =           "";
$settings["google"]["api"]["latitude_callback"] = "http://hitchwiki.org/maps/oauth2";

// Analytic tools
$settings["google"]["analytics_id"] =		""; // ID to enable
$settings["piwik"]["id"] = 					""; // ID to enable

// Facebook
// fb:admins or fb:app_id - A comma-separated list of either the Facebook IDs of page administrators or a Facebook Platform application ID. At a minimum, include only your own Facebook ID.
$settings["fb"]["admins"] = 			"";
$settings["fb"]["page_id"] = 			"";
$settings["fb"]["app"]["id"] = 			"";
$settings["fb"]["app"]["api"] = 		"";
$settings["fb"]["app"]["secret"] = 		"";

// Email credientals for reading incoming mails
$settings["imap"]["server"] =                       "{server:port/imap/ssl/novalidate-cert}INBOX";
$settings["imap"]["username"] =                     "";
$settings["imap"]["password"] =                     "";


// Languages
// See ./admin/ to set up new languages
$settings["default_language"] = 		"en_UK"; // Fall back and default language
$settings["valid_languages"] = 			array( // Remember to add language cells to your database too!
		"en_UK" => "In English", 
		"de_DE" => "Auf Deutsch", 
		"es_ES" => "En Español", 
		"ru_RU" => "По-Pусский",
		"fi_FI" => "Suomeksi", 
		"lt_LT" => "Lietuvių"
);

$settings["languages_in_english"] = 	array(
		"en_UK" => "English", 
		"de_DE" => "German", 
		"es_ES" => "Spanish", 
		"ru_RU" => "Russian",
		"fi_FI" => "Finnish", 
		"lt_LT" => "Lithuanian"
); 


// Usually you don't need to edit this, but you can set it manually, too. No ending "/".
$settings["base_url"] = "http://hitchwiki.org/maps";
$settings["base_url_demo"] 	= "http://hitchwiki.org/devmaps";
#TODO, automate this. "http" . ((!empty($_SERVER['HTTPS'])) ? "s" : "") . "://".$_SERVER['SERVER_NAME'].dirname($_SERVER['REQUEST_URI']);

/*
 * MySQL settings
 */
$mysql_conf = array(
	"user"		=> 		'', 
	"password"	=> 		'',
	"host"		=> 		'',
	"database"	=> 		'',
	"mediawiki_db" => 	'' // the DB where Maps will look for the users info, eg. email
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


/*
 * Allowed page/card names and their settings
 */
$settings["views"] = array(
    "pages" => array(
        "about" => array(
                    "title" => _("About"),
                    "public" => true
                ),
        "add_public_transport" => array(
                    "title" => _("Add a page to the catalog"),
                    "public" => false
                ), 
        "api" => array(
                    "title" => _("API"),
                    "public" => true
                ), 
        "beta" => array(
                    "title" => "",
                    "public" => false
                ),
        "complete_statistics" => array(
                    "title" => _("Complete statistics"),
                    "public" => true
                ), 
        "countries" => array(
                    "title" => _("Countries"),
                    "public" => true
                ), 
        "help" => array(
                    "title" => _("Help & About"),
                    "public" => true
                ), 
        "hitchability" => array(
                    "title" => _("Hitchability"),
                    "public" => true
                ),
        "log_all" => array(
                    "title" => _("Log"),
                    "public" => false
                ),
        "log_place" => array(
                    "title" => _("Log"),
                    "public" => false
                ),
        "log_trips" => array(
                    "title" => _("Log"),
                    "public" => false
                ),
        "log_user" => array(
                    "title" => _("Log"),
                    "public" => false
                ),
        "mobile" => array(
                    "title" => _("Mobile"),
                    "public" => true
                ),
        "news" => array(
                    "title" => _("News"),
                    "public" => true
                ), 
        "own_places" => array(
                    "title" => "",
                    "public" => false
                ), 
        "profile" => array(
                    "title" => _("Profile"),
                    "public" => false
                ),
        "public_transport" => array(
                    "title" => _("Public transport catalog"),
                    "public" => true
                ), 
        "settings" => array(
                    "title" => _("Settings"),
                    "public" => false
                ),         
        "statistics" => array(
                    "title" => _("Statistics"),
                    "public" => true
                ),
        "translate" => array(
                    "title" => _("Help us with translating!"),
                    "public" => true
                ), 
        "trips" => array(
                    "title" => "",
                    "public" => false
                ),
        "trips_countries" => array(
                    "title" => "",
                    "public" => false
                ),
        "trips_import" => array(
                    "title" => "",
                    "public" => false
                ),
        "trips_place" => array(
                    "title" => "",
                    "public" => false
                ),
        "users" => array(
                    "title" => _("Members"),
                    "public" => false
                ),
        "why_register" => array(
                    "title" => _("Why register?"),
                    "public" => true
                ),
        "error404" => array(
                    "title" => _("Error 404 - page not found"),
                    "public" => true
                )
    ),

    "cards" => array(
        "contact",
        "download",
        "link_here",
        "streetview",
        "error404"
    )
);

?>