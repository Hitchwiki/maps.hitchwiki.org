<?php

/* Hitchwiki - maps
 * Global Maps functions
 * 
 * - readURL()
 * - start_sql()
 * - gather_log()
 * - image_map()
 * - error_sign()
 * - info_sign()
 * - bubble_description_html()
 */
require_once("functions_lists.php"); // Lists and statistical
require_once("functions_public_transport.php"); // Public transportation
require_once("functions_place.php"); // Hitchhiking places
require_once("functions_users.php"); // Users
require_once("functions_strings.php"); // Validating / manipulating stings and codes
require_once("functions_trips.php"); // Trips and location handling
require_once("functions_scripts.php"); // Init scripts


/* 
 * cURL
 * Requires http://curl.haxx.se/
 */
function readURL($url) {

	if (function_exists('curl_init')) {

		$ch = curl_init();
		curl_setopt($ch, CURLOPT_URL, $url);
		curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
		curl_setopt($ch, CURLOPT_HEADER, 0);
		$data = curl_exec($ch);
		curl_close($ch);
		
		return $data;
	}
	else return false;
}


/*
 * Start MySQL connection
 */
function start_sql() {
	global $mysql_conf,$link,$settings;

	if(isset($mysql_conf) && !empty($mysql_conf) && !isset($link)) {
		if (!$link = @mysql_connect($mysql_conf['host'], $mysql_conf['user'], $mysql_conf['password'])) {
		    $sql_error = " Could not connect to mysql. \n";
		}
		
		if (!@mysql_select_db($mysql_conf['database'], $link)) {
		    $sql_error .= " Could not select database. \n";
		}
		
		// In case of error, email admins
		if(isset($sql_error)) {

			$headers = 'From: ' . $settings["email"] . "\r\n" .
			    'Reply-To: ' . $settings["email"] . "\r\n" .
			    'X-Mailer: PHP/' . phpversion();

			@mail('mikael.korpela@gmail.com', 'Hitchwiki Maps MySQL error!', $sql_error, $headers);
			
			// Show maintenance screen
			require_once('maintenance_page.php');
			exit;
		}
		else return $link;
	}
	else return false;
} 


/* Mobile icons and startup screens
 * HTML Header function
 */
function mobile_meta($mobile_device=true) {
	global $settings;

	$end = "\n\t";

	$app_icons_and_screens = $settings["base_url"].'/static/mobile/gfx/app_icons-screens/';

	/*
	 * Mobile browsers
	 */
	echo '<link rel="shortcut icon" href="'.$settings["base_url"].'/favicon.png" type="image/png" />'.$end;
	echo '<link rel="bookmark icon" href="'.$settings["base_url"].'/favicon.png" type="image/png" />'.$end;


	/*
	 * Apple devices -- Mobile meta & links
	 * Original https://gist.github.com/472519 by jdaihl
	 *

	Reference:
	
		Custom Icon and Image Creation Guidelines:
		http://developer.apple.com/library/safari/#documentation/UserExperience/Conceptual/MobileHIG/IconsImages/IconsImages.html
		
		Configuring Web Applications:
		http://developer.apple.com/library/safari/#documentation/appleapplications/reference/safariwebcontent/configuringwebapplications/configuringwebapplications.html
		
		Configuring the Viewport:
		http://developer.apple.com/library/safari/#documentation/appleapplications/reference/safariwebcontent/UsingtheViewport/UsingtheViewport.html
		
		Optimizing Web Content:
		http://developer.apple.com/library/safari/#documentation/appleapplications/reference/safariwebcontent/OptimizingforSafarioniPhone/OptimizingforSafarioniPhone.html
	*/
	
	// These only for truly mobile devices
	if($mobile_device) {
	
		// VIEWPORT
	
		// optimized for mobile
		echo '<meta name="viewport" content="width=device-width, initial-scale=1" />'.$end;
		
		// optimized for mobile, zoom/scaling disabled
		echo '<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0" />'.$end;
		
		
		// BROWSER CHROME
		
		// status bar styles: default, black, or black-translucent
		echo '<meta name="apple-mobile-web-app-status-bar-style" content="black" />'.$end;
		
		// hides browser chrome
		echo '<meta name="apple-mobile-web-app-capable" content="yes" />'.$end;
	}
	
	// HOME SCREEN ICONS

	// home screen icon
	echo '<link rel="apple-touch-icon" href="'.$app_icons_and_screens.'icon_57x57.png" />'.$end;
	
	// home screen icon - ipad
	//echo '<link rel="apple-touch-icon" href="'.$app_icons_and_screens.'icon_72x72.png" media="screen and (min-device-width: 481px) and (max-device-width: 1024px)" />'.$end;
	// -- or --
	echo '<link rel="apple-touch-icon" sizes="72x72" href="'.$app_icons_and_screens.'icon_72x72.png" />'.$end;
	
	// home screen icon - high res
	//echo '<link rel="apple-touch-icon" href="/customIcon.png" media="screen and (-webkit-min-device-pixel-ratio: 2)" />'.$end;
	// -- or --
	echo '<link rel="apple-touch-icon" sizes="114x114" href="/icon_114x114.png" />'.$end;
	
	// home screen icon, omits iOS embellishments, works in Android
	//echo '<link rel="apple-touch-icon-precomposed" href="/customIcon.png" />'.$end;
	
	// home screen icon, omits iOS embellishments - ipad
	//echo '<link rel="apple-touch-icon-precomposed" href="/customIcon.png" media="screen and (min-device-width: 481px) and (max-device-width: 1024px)" />'.$end;
	// -- or --
	//echo '<link rel="apple-touch-icon-precomposed" sizes="72x72" href="/customIcon.png" />'.$end;
	
	// home screen icon, omits iOS embellishments - high res
	//echo '<link rel="apple-touch-icon-precomposed" href="/customIcon.png" media="screen and (-webkit-min-device-pixel-ratio: 2)" />'.$end;
	// -- or --
	//echo '<link rel="apple-touch-icon-precomposed" sizes="114x114" href="'.$app_icons_and_screens.'icon-72x72.png" />'.$end;
	
	
	// These only for truly mobile devices
	if($mobile_device) {
	
	// STARTUP IMAGES
	
	// startup image for web apps - iPad - landscape (748x1024) 
	//     Note: iPad landscape startup image has to be exactly 748x1024 pixels (portrait, with contents rotated).-->
	echo '<link rel="apple-touch-startup-image" href="'.$app_icons_and_screens.'startup-landscape_748x1024.png" media="screen and (min-device-width: 481px) and (max-device-width: 1024px) and (orientation:landscape)" />'.$end;
	
	// startup image for web apps - iPad - portrait (768x1004)
	echo '<link rel="apple-touch-startup-image" href="'.$app_icons_and_screens.'startup-portrait_748x1004.png" media="screen and (min-device-width: 481px) and (max-device-width: 1024px) and (orientation:portrait)" />'.$end;
	
	// startup image for web apps (320x460)
	echo '<link rel="apple-touch-startup-image" href="'.$app_icons_and_screens.'startup-portrait_320x460.png" media="screen and (max-device-width: 320px)" />'.$end;

	// startup image for web apps iPod/Iphone high res (640x920)
	// note that in docs mentioned size is 640x960, but it's actually 640x920
	echo '<link rel="apple-touch-startup-image" href="'.$app_icons_and_screens.'startup-portrait_640x920.png" media="(max-device-width: 480px) and (-webkit-min-device-pixel-ratio: 2)" />'.$end;

	}

	/*
	 * Google Devices -- Mobile meta & links
	 */
	echo '<link rel="icon" href="'.$app_icons_and_screens.'icon_32x32.png" sizes="32x32" />'.$end;
	echo '<link rel="icon" href="'.$app_icons_and_screens.'icon_48x48.png" sizes="48x48" />'.$end;
	echo '<meta name="application-name" content="Hitchwiki '._("Maps").'"/>'.$end;
	echo '<meta name="application-url" content="'.$settings["mobile_url"].'"/>'.$end;

}


/*
 * Gather a log array about place/user
 * - descriptions
 * - ratings
 * - waitingtimes
 * - comments
 * - place creations
 */
function gather_log($id=false,$type="place") {

	start_sql();

	$log = array();
	
	// Get a log for a user
	if($id!==false && $type == "user") {
	
	$query = "
		SELECT * FROM 
		(
				SELECT `id`,`ip`,`datetime`,`fk_user`,`fk_point`,
					 `description` AS `log_entry`,
					 `language` AS `log_meta`,
					 'description' AS `log_type`
				FROM `t_points_descriptions` 
				WHERE `fk_user` = ".mysql_real_escape_string($id)." 


			UNION ALL

				SELECT `id`,`ip`,`datetime`,`fk_user`,`fk_point`,
					 `rating` AS `log_entry`,
					 '' AS `log_meta`,
					 'rating' AS `log_type`
				FROM `t_ratings` 
				WHERE `fk_user` = ".mysql_real_escape_string($id)." 
					AND `datetime` IS NOT NULL


			UNION ALL

				SELECT `id`,`ip`,`datetime`,`fk_user`,`fk_point`,
					 `waitingtime` AS `log_entry`,
					 '' AS `log_meta`,
					 'waitingtime' AS `log_type`
				FROM `t_waitingtimes` 
				WHERE `fk_user` = ".mysql_real_escape_string($id)." 
					AND `datetime` IS NOT NULL


			UNION ALL
				
				SELECT `id`,`ip`,`datetime`,`fk_user`,
					 `fk_place` AS `fk_point`,
					 `comment` AS `log_entry`,
					 '' AS `log_meta`,
					 'comment' AS `log_type`
				FROM `t_comments` 
				WHERE `fk_user` = ".mysql_real_escape_string($id)." AND `hidden` IS NULL 
					AND `datetime` IS NOT NULL


			UNION ALL

				SELECT 
					`id` AS `id`,
					`id` AS `fk_point`,
					'' AS `ip`, 
					`datetime`, 
					`user` AS `fk_user`,
					`locality` AS `log_entry`,
					 '' AS `log_meta`,
					'place' AS `log_type`
				FROM `t_points` 
				WHERE `user` = ".mysql_real_escape_string($id)."
						
		) 
		AS `log`
		ORDER BY `datetime` DESC";
			
/*				
			UNION ALL


				SELECT 
					`id`, 
					'' AS `ip`, 
					`datetime`, 
					`user_id` AS `fk_user`,
					'' AS `fk_point`, 
					`country` AS `log_entry`,
					 '' AS `log_meta`,
					'public_transport' AS `log_type`
				FROM `t_ptransport` 
				WHERE `user_id` = ".mysql_real_escape_string($id)."
					AND `datetime` IS NOT NULL


			UNION ALL


				SELECT 
					`id`, 
					'' AS `ip`, 
					`registered` AS `datetime`, 
					`id` AS `fk_user`,
					'' AS `fk_point`, 
					`country` AS `log_entry`,
					 '' AS `log_meta`,
					'user' AS `log_type`
				FROM `t_users` 
				WHERE `id` = ".mysql_real_escape_string($id)."
					AND `registered` IS NOT NULL

*/

	
	}
	// Get a log for a place
	elseif($id!==false && $type == "place") {
	
	$query = "
		SELECT * FROM 
		(
				SELECT `id`,`ip`,`datetime`,`fk_user`,`fk_point`,
					 `description` AS `log_entry`,
					 `language` AS `log_meta`,
					 'description' AS `log_type`
				FROM `t_points_descriptions` 
				WHERE `fk_point` = ".mysql_real_escape_string($id)." 


			UNION ALL

				SELECT `id`,`ip`,`datetime`,`fk_user`,`fk_point`,
					 `rating` AS `log_entry`,
					 '' AS `log_meta`,
					 'rating' AS `log_type`
				FROM `t_ratings` 
				WHERE `fk_point` = ".mysql_real_escape_string($id)." 
					AND `datetime` IS NOT NULL


			UNION ALL

				SELECT `id`,`ip`,`datetime`,`fk_user`,`fk_point`,
					 `waitingtime` AS `log_entry`,
					 '' AS `log_meta`,
					 'waitingtime' AS `log_type`
				FROM `t_waitingtimes` 
				WHERE `fk_point` = ".mysql_real_escape_string($id)." 
					AND `datetime` IS NOT NULL


			UNION ALL
				
				SELECT `id`,`ip`,`datetime`,`fk_user`,
					 `fk_place` AS `fk_point`,
					 `comment` AS `log_entry`,
					 '' AS `log_meta`,
					 'comment' AS `log_type`
				FROM `t_comments` 
				WHERE `fk_place` = ".mysql_real_escape_string($id)." AND `hidden` IS NULL 
					AND `datetime` IS NOT NULL


			UNION ALL

				SELECT 
					`id` AS `id`, 
					`id` AS `fk_point`,
					'' AS `ip`, 
					`datetime`, 
					`user` AS `fk_user`,
					`locality` AS `log_entry`,
					 '' AS `log_meta`,
					'place' AS `log_type`
				FROM `t_points` 
				WHERE `id` = ".mysql_real_escape_string($id)."
				
		) 
		AS `log`
		ORDER BY `datetime` DESC";
	
	}
	// Get everything what's happening on the site
	else {
		$query = "SELECT * FROM 
		(
		
				SELECT `id`,`ip`,`datetime`,`fk_user`,`fk_point`,
					 `description` AS `log_entry`,
					 `language` AS `log_meta`,
					 'description' AS `log_type`
				FROM `t_points_descriptions` 
				WHERE DATE_SUB(CURDATE(),INTERVAL 7 DAY) <= datetime 
					AND `datetime` IS NOT NULL


			UNION ALL


				SELECT `id`,`ip`,`datetime`,`fk_user`,`fk_point`,
					 `rating` AS `log_entry`,
					 '' AS `log_meta`,
					 'rating' AS `log_type`
				FROM `t_ratings` 
				WHERE DATE_SUB(CURDATE(),INTERVAL 7 DAY) <= datetime 
					AND `datetime` IS NOT NULL


			UNION ALL


				SELECT `id`,`ip`,`datetime`,`fk_user`,`fk_point`,
					 `waitingtime` AS `log_entry`,
					 '' AS `log_meta`,
					 'waitingtime' AS `log_type`
				FROM `t_waitingtimes` 
				WHERE DATE_SUB(CURDATE(),INTERVAL 7 DAY) <= datetime 
					AND `datetime` IS NOT NULL


			UNION ALL


				SELECT `id`,`ip`,`datetime`,`fk_user`,
					 `fk_place` AS `fk_point`,
					 `comment` AS `log_entry`,
					 '' AS `log_meta`,
					 'comment' AS `log_type`
				FROM `t_comments` 
				WHERE DATE_SUB(CURDATE(),INTERVAL 7 DAY) <= datetime 
					AND `datetime` IS NOT NULL
					AND `hidden` IS NULL


			UNION ALL


				SELECT 
					`id`, 
					'' AS `ip`, 
					`datetime`, 
					`user_id` AS `fk_user`,
					'' AS `fk_point`, 
					`country` AS `log_entry`,
					 '' AS `log_meta`,
					'public_transport' AS `log_type`
				FROM `t_ptransport` 
				WHERE DATE_SUB(CURDATE(),INTERVAL 7 DAY) <= datetime 
					AND `datetime` IS NOT NULL


			UNION ALL


				SELECT 
					`id`, 
					'' AS `ip`, 
					`registered` AS `datetime`, 
					`id` AS `fk_user`,
					'' AS `fk_point`, 
					`country` AS `log_entry`,
					 '' AS `log_meta`,
					'user' AS `log_type`
				FROM `t_users` 
				WHERE DATE_SUB(CURDATE(),INTERVAL 7 DAY) <= registered 
					AND `registered` IS NOT NULL


			UNION ALL


				SELECT 
					`id`, 
					`id` AS `fk_point`, 
					'' AS `ip`, 
					`datetime`, 
					`user` AS `fk_user`,
					`locality` AS `log_entry`,
					 '' AS `log_meta`,
					'place' AS `log_type`
				FROM `t_points` 
				WHERE DATE_SUB(CURDATE(),INTERVAL 7 DAY) <= datetime 
					AND `datetime` IS NOT NULL
				
		)
		AS `log`
		ORDER BY `datetime` DESC";
	}
	
	start_sql();
	$res = mysql_query($query);
	
	if(!$res) return false;
	
	#if(mysql_num_rows($res) > 0) {
		while($line = mysql_fetch_array($res, MYSQL_ASSOC)) {
			$log[] = $line;
		}
	#}

	if(!empty($log)) return $log;
	else return false;
}


/*
 * Produce an URL to image map
 * Requires: 
 * - lat
 * - lon
 *
 * Optional:
 * - zoom
 * - format (png|jpg|gif)
 * - width (in px, max 2048)
 * - height (in px, max 2048)
 *
 * returns an url to the image from openstreetmap via open mapquestapi
 * http://open.mapquestapi.com/staticmap/
 */
function image_map($lat, $lon, $zoom=15, $format='png', $width=150, $height=150, $type='map') {

	if(!validate_lon($lon) OR !validate_lat($lat) OR $zoom===false OR $zoom < 0 OR $width <= 0 OR $height <= 0) 
	  return false;

	elseif($format != 'png' && $format != 'jpeg' && $format != 'jpg' && $format != 'gif') 
	  return false;

	elseif($type != 'map' && $type != 'sat' && $type != 'hyb') 
	  return false;

	else
	//		   'http://open.mapquestapi.com/staticmap/v3/getmap?size=600,200&zoom=14&shapeformat=cmp&center=40.770021,-73.984003&shape=y_zwFjsrbMxWkz@??}DoC??a@}CyBt@ySiN??fDeP&scenter=40.77069,-73.992378&ecenter=40.770935,-73.97644';
		return 'http://open.mapquestapi.com/staticmap/v3/getmap?size='.urlencode($width).','.urlencode($height).'&zoom='.urlencode($zoom).'&center='.urlencode($lat).','.urlencode($lon).'&type='.$type.'&imageType='.$format; 
	  //return 'http://tah.openstreetmap.org/MapOf/?lat='.urlencode($lat).'&long='.urlencode($lon).'&z='.urlencode($zoom).'&w='.urlencode($width).'&h='.urlencode($height).'&skip_attr=on&format='.urlencode($format);

}


/*
 * Print out an error sign
 */
function error_sign($msg=false, $hide=true) {
	global $settings;
	
	$random = time();
	
	$title = _("Error");
	if(!empty($msg)) {
		$title .= ":";
		$msg = htmlspecialchars($msg);
	} else $msg = "";
	
	// Print error sign
	if($settings["mobile"]) {
		echo '<div class="ui-body ui-body-e" style="padding: 0 .7em; margin: 10px 0;" id="error_'.$random.'">'. 
		    '<p><strong>'.$title.'</strong><br/><span class="error_text">'.$msg.'</span></p>'.
		    '</div>';
	} else {
		echo '<div class="ui-state-error ui-corner-all" style="padding: 0 .7em; margin: 10px 0;" id="error_'.$random.'">'. 
		    '<p><span class="ui-icon ui-icon-alert" style="float: left; margin-right: .3em;"></span> '.
		    '<strong>'.$title.'</strong> <span class="error_text">'.$msg.'</span></p>'.
		    '</div>';
	}
	
	// Hides error
	if($hide==true) {
		echo '<script type="text/javascript">'.
				'$(function(){'.
					'$("#error_'.$random.'").delay(2500).fadeOut("slow");'.
				'});'.
			'</script>';
	}
}

/*
 * Print out an info sign
 */
function info_sign($msg=false, $hide=true) {

	$random = time();

	if(!empty($msg)) {

		// Print info sign
		if($settings["mobile"]) {
			echo '<div class="ui-body ui-body-e" style="padding: 0 .7em; margin: 10px 0;" id="info_'.$random.'">'. 
			    '<p><span class="info_text">'.htmlspecialchars($msg).'</span></p>'.
			    '</div>';
		} else {
			echo '<div class="ui-state-highlight ui-corner-all" style="padding: 0 .7em; margin: 20px 0;" id="info_'.$random.'">'. 
			    '<p><span class="ui-icon ui-icon-info" style="float: left; margin-right: .3em;"></span>  '.
			    '<span class="info_text">'.htmlspecialchars($msg).'</span></p>'.
			    '</div>';
		}

		// Hides info
		if($hide==true) {
			echo '<script type="text/javascript">'.
					'$(function(){'.
						'$("#info_'.$random.'").delay(2500).fadeOut("slow");'.
					'});'.
				'</script>';
		} // hide?

	} // !empty
}


/*
 * Output description in HTML form for map bubbles (eg. for KML-files)
 */
function bubble_description_html($marker) {
	global $settings;
   $lang = $settings["default_language"];

   if(!empty($marker["description"][$lang]["description"])) $return .= Markdown($marker["description"][$lang]["description"]).' ';

   // Meta START		
   $return .= "\n".'<div style="border-top: 1px solid #ccc; margin: 5px 0 0 0; padding: 5px 0 0 0;"><small>';

   // Meta: rating
   $return .= '<b>'._("Hitchability").':</b> '.hitchability2textual($marker["rating"]).' <b style="font-size: 15px; color: #'.$settings["hitchability_colors"][$marker["rating"]].';">&bull;</b> ('; 
   $return .= sprintf(ngettext("%d vote", "%d votes", $marker["rating_stats"]["rating_count"]), $marker["rating_stats"]["rating_count"]);
   $return .= ')<br />';

   if($marker["rating_stats"]["rating_count"] > 1) {
       $return .= _("Vote distribution").':<br />';
       $return .= '<img src="'.rating_chart($marker["rating_stats"], 220).'" alt="'._("Vote distribution").'" /><br />';
   }

   // Meta: Waitingtime
   if($marker["waiting_stats"]["count"] > 0) {
       $return .= '<b title="'._("Average").'">'._("Waiting time").':</b> ';
       $return .= $marker["waiting_stats"]["avg_textual"].' ('; 
       $return .= sprintf(ngettext("%d experience", "%d experiences", $marker["waiting_stats"]["count"]), $marker["waiting_stats"]["count"]);
       $return .= ')<br />';
   }

   // Meta: edited time
   if(!empty($marker["description"][$lang]["datetime"])) {
       $return .= '<span title="'.date(DATE_RFC822,strtotime($marker["description"][$lang]["datetime"])).'">';
       $return .= sprintf(_('Description written %s'), date("j.n.Y",strtotime($marker["description"][$lang]["datetime"])));
       $return .= '</span><br />';
   }

   // Meta: link				
   if(!empty($marker["link"])) $return .= '<a href="'.$marker["link"].'">'._("Place in Hitchwiki Maps").'</a><br />';

   // Meta END
   $return .= "</small></div>\n";

   return $return;
}


?>