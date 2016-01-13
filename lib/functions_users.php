<?php
/* Hitchwiki - maps
 * User functions
 * - username()
 * - current_user()
 * - user_info()
 * - get_user()
 */


/* 
 * Return a user name by ID
 */
function username($id, $link=false) {

	if(is_id($id)) {
		start_sql();
		
		// Get users name from database
		$res = mysql_query("SELECT `id`,`name` FROM `t_users` WHERE `id` = ".mysql_real_escape_string($id)." LIMIT 1");
		if(!$res) return _("Anonymous");
		
		// If we have a result, go and get the name
		if(mysql_num_rows($res) > 0) {
		    while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
		    	if($link===true) return user_link($id, $r["name"]);
		    	else return htmlspecialchars($r["name"]);
		    }
		}
		else return _("Anonymous");
	}
	else return _("Anonymous");
}


/* 
 * Return a link to user's page
 */
function user_link($id=false, $username=false) {
	global $settings, $user; 
	
	if(!empty($id) && !empty($username)) {
	
		$title = (!empty($user["id"]) && $user["id"] == $waitingtime["user_id"]) ? _("That's you!") : _("Profile");
	
		return '<a href="'.$settings["base_url"].'/profile/'.$id.'/" onclick="open_page(\'profile\', \'user_id='.$id.'\'); return false;" title="'.$title.'">'.htmlspecialchars($username).'</a>';

	}
	else return '<!-- error when printing profile link -->';
}


/* 
 * Return info about logged in user
 * or return false if user isn't logged in
 */
function current_user($get_password=false) {
	global $_SESSION;
	
	if(isset($_SESSION["wsUserID"]) && !empty($_SESSION["wsUserID"])) return get_user($_SESSION);
	else return false;
}



/*
 * Get user's infoarray by ID
 */
function user_info($user_id) {
	global $settings;

	start_sql();

	$res = mysql_query("SELECT * FROM `t_users` WHERE `id` = '".mysql_real_escape_string($user_id)."' LIMIT 1");
   	
   	if(!$res) return false;
			
	// If we have a result, continue gathering user array
	if(mysql_num_rows($res) > 0) {
		while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {

			$user["logged_in"] = true;
			$user["id"] = $r["id"];
			$user["name"] = $r["name"];
			$user["location"] = $r["location"];
			$user["country"] = $r["country"];
			$user["language"] = $r["language"];
			$user["registered"] = $r["registered"];
			$user["last_seen"] = $r["last_seen"];
			$user["private_location"] = $r["private_location"];
			#$user["private_trips"] = false;
			$user["google_latitude"] = $r["google_latitude"];
			$user["centered_glatitude"] = $r["centered_glatitude"];
			$user["allow_gravatar"] = $r["allow_gravatar"];
			$user["disallow_facebook"] = $r["disallow_facebook"];
			$user["map_google"] = $r["map_google"];
			$user["map_ovi"] = $r["map_ovi"];
			$user["map_bing"] = $r["map_bing"];
			$user["map_default_layer"] = $r["map_default_layer"];
			
			// Admin?
			if($r["admin"]=="1" && $settings["allow_admins"] === true) $user["admin"] = true;
			else $user["admin"] = false;

			return $user;
		}
	} else return false;
   	
}



/*
 * Check if user is in database
 * email = t_user.email
 * password = md5(t_user.password)
 */
function get_user($session=false) {
	global $settings;

	if(empty($session["wsUserID"]) OR $session === false) return false;
	
	start_sql();
	$res = @mysql_query("SELECT * FROM `t_users` WHERE `id` = '".mysql_real_escape_string($session["wsUserID"])."' LIMIT 1");
   	
   	if(!$res) return false;
			
	// If we have a result, continue gathering user array
	if(@mysql_num_rows($res) > 0) {

		$last_seen = @mysql_query("UPDATE `t_users` SET `last_seen` = NOW() WHERE `id` = ".mysql_real_escape_string($session["wsUserID"])." LIMIT 1");

		while($r = @mysql_fetch_array($res, MYSQL_ASSOC)) {

			$user["logged_in"] = true;
			$user["id"] = $session["wsUserID"];
			$user["name"] = $session["wsUserName"];
			$user["location"] = $r["location"];
			$user["country"] = $r["country"];
			$user["language"] = $r["language"];
			$user["registered"] = $r["registered"];
			$user["last_seen"] = $r["last_seen"];
			$user["private_location"] = $r["private_location"];
			#$user["private_trips"] = false;
			$user["google_latitude"] = $r["google_latitude"];
			$user["centered_glatitude"] = $r["centered_glatitude"];
			$user["allow_gravatar"] = $r["allow_gravatar"];
			$user["disallow_facebook"] = $r["disallow_facebook"];
			$user["map_google"] = $r["map_google"];
			$user["map_ovi"] = $r["map_ovi"];
			$user["map_bing"] = $r["map_bing"];
			$user["map_default_layer"] = $r["map_default_layer"];
			
			// Admin?
			if($r["admin"]=="1" && isset($settings["allow_admins"]) && $settings["allow_admins"] === true) $user["admin"] = true;
			else $user["admin"] = false;
			
			// If the name in the session was different than the one in DB, update DB
			if($r["name"] != $session["wsUserName"] && !empty($session["wsUserName"])) {
				$res = mysql_query("UPDATE `t_users` SET `name` = '".mysql_real_escape_string($session["wsUserName"])."' WHERE `id` = ".mysql_real_escape_string($session["wsUserID"])." LIMIT 1");
			}
			
			return $user;
		}
	}
	// If user by that ID didn't exist, create a new row for the user 
	else {
		global $mysql_conf;
	
		/*
		 * Copy user email from the mediawiki DB
		 */ 
		$mw_link = @mysql_connect($mysql_conf['host'], $mysql_conf['user'], $mysql_conf['password']);
		@mysql_select_db($mysql_conf["mediawiki_db"], $mw_link);

		$mw_res = @mysql_query("SELECT `user_id`,`user_name`,`user_email` FROM `".$mysql_conf["mediawiki_db"]."`.`user` WHERE user_id = ".mysql_real_escape_string($session["wsUserID"])." LIMIT 1");

		if(@mysql_num_rows($mw_res) > 0) {
			while($mw_r = @mysql_fetch_array($mw_res, MYSQL_ASSOC)) {
			    $email = "'".$mw_r["user_email"]."'";
			}
		}
		else $email = "NULL";
		
	
		/*
		 * Add new user to the Maps DB
		 */
		if(!empty($session["wsUserName"])) {
			start_sql();
			$query = "INSERT INTO `".$mysql_conf['database']."`.`t_users` (
					`id`,
					`name`,
					`email`,
					`registered`,
					`last_seen`
				) VALUES (
					".mysql_real_escape_string($session["wsUserID"]).", 
					'".mysql_real_escape_string(htmlspecialchars($session["wsUserName"]))."', 
					".$email.",
					NOW(),
					NOW()
				);";
				
			$res = @mysql_query($query);
		   
			if(!$res) return false;
			else return get_user($session);
		}
		else return false;
	}

}


?>
