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
		if($_POST["user_id"] != $user["id"]) { echo json_encode( array("error"=>"You don't have permission to update settings for this user.") ); exit; }
	}
	else { echo json_encode( array("error"=>_("Missing user ID.")) ); exit; }

	
	// Language
	if(!empty($_POST["language"])) {
		if(!isset($settings["valid_languages"][$_POST["language"]])) { echo json_encode( array("error"=>_("Illegal language code; ".htmlspecialchars($_POST["language"]).".")) ); exit; }
	
		$language = "'".mysql_real_escape_string($_POST["language"])."'";
	}
	else $language = 'NULL';
	
	
	// Location
	$location = (!empty($_POST["location"])) ? "'".mysql_real_escape_string($_POST["location"])."'": 'NULL';
	
	
	// Country
	if(!empty($_POST["country"])) {
		$valid_countries = countrycodes();
		if(!isset($valid_countries[$_POST["country"]])) { echo json_encode( array("error"=>_("Illegal country code; ".htmlspecialchars($_POST["country"]).".")) ); exit; }
		
		$country = "'".mysql_real_escape_string($_POST["country"])."'";
	}
	else $country = 'NULL';
	
	
	// Private location
	$private_location = ($_POST["private_location"] == "true") ? '1': 'NULL';
	
	// Google Latitude
	if(!empty($_POST["google_latitude"])) $google_latitude = "'".mysql_real_escape_string($_POST["google_latitude"])."'";
	else $google_latitude = 'NULL';
	
	// Centered to Google Latitude
	$centered_glatitude = ($_POST["centered_glatitude"] == "true") ? '1': 'NULL';
	
	// Allow Gravatar
	$allow_gravatar = ($_POST["allow_gravatar"] == "true") ? '1': 'NULL';
	
	// Disallow Facebook
	$disallow_facebook = ($_POST["disallow_facebook"] == "true") ? '1': 'NULL';
	
	// Map layer: google
	$map_google = ($_POST["map_google"] == "true") ? '1': 'NULL';
	
	// Map layer: yahoo
	$map_yahoo = ($_POST["map_yahoo"] == "true") ? '1': 'NULL';
	
	// Map layer: virtual earth
	$map_vearth = ($_POST["map_vearth"] == "true") ? '1': 'NULL';
	
	// Default map layer
	$map_default_layer = (!empty($_POST["map_default_layer"])) ? "'".mysql_real_escape_string($_POST["map_default_layer"])."'": 'NULL';


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
	    		`disallow_facebook` = ".$disallow_facebook.",
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