<?php
/*
 * Hitchwiki Maps: user_settings.php
 * To register new people and to change settings of registered people
 */

/*
 * Load config to set language and stuff
 */
require_once "../config.php";

start_sql();

 
/*
 * Validate fields
 */
 
	// User ID
	if(isset($_POST["user_id"])) {
		// Id is ok?
		if(empty($_POST["user_id"]) && !is_numeric($_POST["user_id"])) { echo json_encode( array("error"=>_("Invalid user ID.")) ); exit; }
		
		// Check if it's current user who is updating this, include a password with info array
		$user = current_user(true);
		if($_POST["user_id"] != $user["id"]) { echo json_encode( array("error"=>_("You don't have permission do update settings for this user.")) ); exit; }
	}
	else { echo json_encode( array("error"=>_("Missing user ID.")) ); exit; }

	
	// Language
	if(!empty($_POST["language"])) {
		if(!isset($settings["valid_languages"][$_POST["language"]])) { echo json_encode( array("error"=>_("Illegal language code; ".htmlspecialchars($_POST["language"]).".")) ); exit; }
	
		$language = "'".mysql_real_escape_string($_POST["language"])."'";
	}
	else $language = 'NULL';
	
	
	// Location
	if(!empty($_POST["location"])) $location = "'".mysql_real_escape_string($_POST["location"])."'";
	else $location = 'NULL';
	
	
	// Country
	if(!empty($_POST["country"])) {
		$valid_countries = countrycodes();
		if(!isset($valid_countries[$_POST["country"]])) { echo json_encode( array("error"=>_("Illegal country code; ".htmlspecialchars($_POST["country"]).".")) ); exit; }
		
		$country = "'".mysql_real_escape_string($_POST["country"])."'";
	}
	else $country = 'NULL';
	
	
	// Private location
	if($_POST["private_location"] == "true") $private_location = '1';
	else $private_location = 'NULL';
	
	// Google Latitude
	if(!empty($_POST["google_latitude"])) $google_latitude = "'".mysql_real_escape_string($_POST["google_latitude"])."'";
	else $google_latitude = 'NULL';
	
	// Centered to Google Latitude
	if($_POST["centered_glatitude"] == "true") $centered_glatitude = '1';
	else $centered_glatitude = 'NULL';
	
	// Allow Gravatar
	if($_POST["allow_gravatar"] == "true") $allow_gravatar = '1';
	else $allow_gravatar = 'NULL';
	
	// Map layer: google
	if($_POST["map_google"] == "true") $map_google = '1';
	else $map_google = 'NULL';
	
	// Map layer: yahoo
	if($_POST["map_yahoo"] == "true") $map_yahoo = '1';
	else $map_yahoo = 'NULL';
	
	// Map layer: virtual earth
	if($_POST["map_vearth"] == "true") $map_vearth = '1';
	else $map_vearth = 'NULL';
	
	// Default map layer
	if(!empty($_POST["map_default_layer"])) $map_default_layer = "'".mysql_real_escape_string($_POST["map_default_layer"])."'";
	else $map_default_layer = 'NULL';


/*
 * Proceed to the database stuff
 */

	$query = "UPDATE `t_users` SET 
	    		`name` = '".mysql_real_escape_string($_POST["name"])."',";
	
	if(isset($password)) $query .= "`password` = '".$password."',";
	
	$query .= "	`email` = '".mysql_real_escape_string($_POST["email"])."',
	    		`location` = ".$location.",
	    		`country` = ".$country.",
	    		`language` = ".$language.", 
	    		`private_location` = ".$private_location.",
	    		`google_latitude` = ".$google_latitude.",
	    		`centered_glatitude` = ".$centered_glatitude.",
	    		`allow_gravatar` = ".$allow_gravatar.",
				`map_google` = ".$map_google.",
				`map_yahoo` = ".$map_yahoo.",
				`map_vearth` = ".$map_vearth.",
				`map_default_layer` = ".$map_default_layer."
	    	WHERE `id` = ".mysql_real_escape_string($_POST["user_id"])." LIMIT 1;";
	
	$res = mysql_query($query);   
	if(!$res) { echo json_encode( array("error"=>_("Oops! Something went wrong! Try again.")) ); exit; } 
	
	
// If we made it this far... plop out our success!
$output["success"] = true;
echo json_encode($output);

?>