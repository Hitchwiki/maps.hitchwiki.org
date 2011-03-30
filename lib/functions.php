<?php

/* Hitchwiki - maps
 * Global Maps functions
 * 
 */
 
 
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
		    /*
			$headers = 'From: ' . $settings["email"] . "\r\n" .
			    'Reply-To: ' . $settings["email"] . "\r\n" .
			    'X-Mailer: PHP/' . phpversion();

			mail('mikael@ihminen.org', 'Hitchwiki Maps MySQL error!', $sql_error, $headers);
			*/
			// Show maintenance screen
			require_once('maintenance_page.php');
			exit;
		}
		else return $link;
	}
	else return false;
} 



/*
 * Get a place array by ID
 * id: INT (required)
 * wide: true | false (default) - gets more info than just basics
 */
function get_place($id=false, $more=false) {
	global $settings;
	start_sql();

	if(preg_match ("/^([0-9]+)$/", $id) && !empty($id)) {

		$place["id"] = $id;
		 
		$query = "SELECT 
					`id`,
					`user`, 
					`type`,
					`lat`,
					`lon`,
					`rating`,
					`waitingtime`,
					`waitingtime_count`";
		 
		// Get more wider set of info
		if($more==true) {
		 
			$query .= ",
						`elevation`,
						`rating_count`,
			    		`country`,
			    		`continent`,
			    		`locality`,
			    		`datetime`";
									
			// Add all available languages to the query
			/*
			foreach($settings["valid_languages"] as $code => $name) {
				$query .= ",`".$code."`";
			}
			*/
			
		}//if more end
		
		$query .= " FROM `t_points` 
		    		WHERE `type` = 1 AND `id` = ".mysql_real_escape_string($id)."
		    		LIMIT 1";

		$res = mysql_query($query);
		
		
		// Return error for no result
		if(!$res OR mysql_affected_rows() <= 0) {
			$place["error"] = true;
			return $place;
		}
		
		// Loop data in to an array
		while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
		    
		 	$place["lat"] = $r["lat"];
		 	$place["lon"] = $r["lon"];
		 	
		 	if($more==true) {
		 		$place["elevation"] = $r["elevation"];
		 		$place["location"]["locality"] = $r["locality"];
		 		$place["location"]["country"]["iso"] = $r["country"];
		 		$place["location"]["country"]["name"] = ISO_to_country($r["country"]);
		 		$place["location"]["continent"]["code"] = $r["continent"];
		 		$place["location"]["continent"]["name"] = continent_name($r["continent"]);
		 		
		 		if(!empty($r["user"])) {
			 		$place["user"]["id"] = $r["user"];
			 		$place["user"]["name"] = username($r["user"]);
				}
				
		 		$place["link"] = $settings["base_url"]."/?place=".$id;
		 		$place["datetime"] = $r["datetime"];
		 		
		 		// Loop trough descriptions in different languages
		 		/*
		 		foreach($settings["valid_languages"] as $code => $name) {
		 			$place["description"][$code] = stripslashes($r[$code]);
		 		}
		 		*/
		
		 		
		 	} // end more
		 	
		 	// Nice to have ratings at this point, but continue $more after this...
		 	$place["rating"] = $r["rating"];

			if($more==true) {
	
				// Get stats about ratings if we know there are more than one
				if($r["rating_count"] > 1) {
					
					$place["rating_stats"] = rating_stats($id);
					
				} // end if more than 1
				else {
					$place["rating_stats"]["rating_count"] = $r["rating_count"];
				}
					
					
		 		$place["waiting_stats"]["avg"] = $r["waitingtime"];
		 		$place["waiting_stats"]["avg_textual"] = nicetime($r["waitingtime"]);
					
				// Get stats about waitingtimes if we know there are more than one
				if($r["waitingtime_count"] > 1) {
					
					$place["waiting_stats"] = waitingtimes($id);
					
				} // end if more than 1
				else {
					$place["waiting_stats"]["count"] = $r["waitingtime_count"];
				}


				// Descreptions from a seperate table
				$query2 = "SELECT *, COUNT(*) AS languages_count FROM 
							(
								SELECT 
									`id`,
									`datetime`, 
									`fk_point`,
									`fk_user`,
									`language`, 
									`description` 
		    					
								FROM `t_points_descriptions` 
								WHERE `fk_point` = ".mysql_real_escape_string($id)." 
								ORDER BY `datetime` DESC
							) 
							AS `t_points_descriptions_tmp`
							
							GROUP BY `language`
							
							ORDER BY `language` DESC";
								
				$res2 = mysql_query($query2);
				while($r2 = mysql_fetch_array($res2, MYSQL_ASSOC)) {
				
					// In DB we have these fields: id, datetime, language, fk_point, fk_user, ip, description
					$place["description"][$r2["language"]]["datetime"] = $r2["datetime"];
					$place["description"][$r2["language"]]["fk_user"] = $r2["fk_user"];
					$place["description"][$r2["language"]]["description"] = $r2["description"];
					$place["description"][$r2["language"]]["versions"] = $r2["languages_count"];
				
				
				}



				// Comments
		 		$place["comments"] = get_comments($id);
		 		$place["comments_count"] = count($place["comments"]);
			} // end more
		
		} // while end
		
   
   		// output
   		return $place;
   
	}
	else {
		// ID wasn't valid
		return false;
	}

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

	$log = array();
	
	// Get a log for a user
	if($id!==false && $type == "user") {
	
	$query = "
		SELECT * FROM 
		(
				SELECT `id`,`ip`,`datetime`,`fk_user`,
					 `description` AS `log_entry`,
					 `language` AS `log_meta`,
					 'description' AS `log_type`
				FROM `t_points_descriptions` 
				WHERE `fk_user` = ".mysql_real_escape_string($id)." 


			UNION ALL

				SELECT `id`,`ip`,`datetime`,`fk_user`,
					 `rating` AS `log_entry`,
					 '' AS `log_meta`,
					 'rating' AS `log_type`
				FROM `t_ratings` 
				WHERE `fk_user` = ".mysql_real_escape_string($id)." 
					AND `datetime` IS NOT NULL


			UNION ALL

				SELECT `id`,`ip`,`datetime`,`fk_user`,
					 `waitingtime` AS `log_entry`,
					 '' AS `log_meta`,
					 'waitingtime' AS `log_type`
				FROM `t_waitingtimes` 
				WHERE `fk_user` = ".mysql_real_escape_string($id)." 
					AND `datetime` IS NOT NULL


			UNION ALL
				
				SELECT `id`,`ip`,`datetime`,`fk_user`,
					 `comment` AS `log_entry`,
					 '' AS `log_meta`,
					 'comment' AS `log_type`
				FROM `t_comments` 
				WHERE `fk_user` = ".mysql_real_escape_string($id)." AND `hidden` IS NULL 
					AND `datetime` IS NOT NULL


			UNION ALL

				SELECT 
					`id` AS `id`, 
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
				SELECT `id`,`ip`,`datetime`,`fk_user`,
					 `description` AS `log_entry`,
					 `language` AS `log_meta`,
					 'description' AS `log_type`
				FROM `t_points_descriptions` 
				WHERE `fk_point` = ".mysql_real_escape_string($id)." 


			UNION ALL

				SELECT `id`,`ip`,`datetime`,`fk_user`,
					 `rating` AS `log_entry`,
					 '' AS `log_meta`,
					 'rating' AS `log_type`
				FROM `t_ratings` 
				WHERE `fk_point` = ".mysql_real_escape_string($id)." 
					AND `datetime` IS NOT NULL


			UNION ALL

				SELECT `id`,`ip`,`datetime`,`fk_user`,
					 `waitingtime` AS `log_entry`,
					 '' AS `log_meta`,
					 'waitingtime' AS `log_type`
				FROM `t_waitingtimes` 
				WHERE `fk_point` = ".mysql_real_escape_string($id)." 
					AND `datetime` IS NOT NULL


			UNION ALL
				
				SELECT `id`,`ip`,`datetime`,`fk_user`,
					 `comment` AS `log_entry`,
					 '' AS `log_meta`,
					 'comment' AS `log_type`
				FROM `t_comments` 
				WHERE `fk_place` = ".mysql_real_escape_string($id)." AND `hidden` IS NULL 
					AND `datetime` IS NOT NULL


			UNION ALL

				SELECT 
					`id` AS `id`, 
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


				SELECT `id`,`ip`,`datetime`,`fk_user`,`fk_place` AS `fk_point`,
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
 * Update rating quick access info
 */
function update_rating_stats($place_id) {

	if($place_id==false) return false;

	// start_sql(); and get array of stats
	$rating_stats = rating_stats($place_id); 

   	if($rating_stats !== false) {
   	    $res = mysql_query("UPDATE `t_points` SET `rating` = '".mysql_real_escape_string(round($rating_stats["exact_rating"]))."',`rating_count` = '".mysql_real_escape_string($rating_stats["rating_count"])."' WHERE `id` = ".mysql_real_escape_string($place_id)." LIMIT 1;");

   	    if(!$res) return false;
   	    else return true;
   	}
   	else return false;
}



/*
 * Get rating statistics for a place
 * id: fk_point in t_ratings (required)
 */
function rating_stats($place_id=false) {
	start_sql();
	
	$query = "SELECT `fk_user`,`fk_point`,`rating`,
		    COUNT(DISTINCT rating) AS different_ratings,
		    COUNT(*) AS ratings_count,	
		    AVG(rating) AS avg_rating
		    FROM t_ratings ";
		    
	if($place_id!==false && !empty($place_id) && is_numeric($place_id)) $query .= "WHERE `fk_point` = ".mysql_real_escape_string($place_id);
	
	$query .= " GROUP BY rating WITH ROLLUP";
	
	$stats = array();
	$res = mysql_query($query);
	while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
	
	    // It's inforow collected from all ratings
	    if(empty($r["rating"])) {
	    	$stats["exact_rating"] = $r["avg_rating"];
	    	$stats["rating_count"] = $r["ratings_count"];
	    	$stats["different_ratings"] = $r["different_ratings"];
	    }
	    // Single rating number 1-5
	    else {
	    	$stats["ratings"][$r["rating"]]["rating"] = $r["rating"];
	    	$stats["ratings"][$r["rating"]]["rating_count"] = $r["ratings_count"];
	    }
	}
	
	return $stats;
}


/*
 * Get waiting time statistics for a place
 * id: fk_point in t_waitingtimes (required)
 */
function waitingtimes($place_id=false) {

	
	$query = "SELECT `fk_user`,`fk_point`,`waitingtime`,
		    COUNT(DISTINCT waitingtime) AS different_times,
		    COUNT(*) AS count,	
		    AVG(waitingtime) AS avg
		    FROM t_waitingtimes ";
		    
	if($place_id!==false && !empty($place_id) && is_numeric($place_id)) $query .= "WHERE `fk_point` = ".mysql_real_escape_string($place_id);
	
	
	$query .= " GROUP BY waitingtime WITH ROLLUP";
	
	$stats = array();
	$res = mysql_query($query);
	while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
	
	    // It's inforow collected from all waitingtimes
	    if(empty($r["waitingtime"])) {
	    	$stats["avg"] = round($r["avg"]);
	    	$stats["avg_textual"] = nicetime(round($r["avg"]));
	    	$stats["count"] = $r["count"];
	    	$stats["different_times"] = $r["different_times"];
	    }
	    /*
	    else {
	    	$stats["times"][$r["waitingtime"]]["minutes"] = $r["waitingtime"];
	    	$stats["times"][$r["waitingtime"]]["count"] = $r["count"];
	    }
	    */
	}
	
	return $stats;
	
}


/* 
 * List comments to the place by ID or just all there are in DB
 * Returns an array
 *
 * ID: place ID (Not comment ID)
 * limit: how many rows will be returned, eg: "3" or "1,3"
 */
function get_comments($id=false, $limit=false) {
	global $user;


	// Start building a query
	$query = "SELECT `id`,`fk_place`,`fk_user`,`nick`,`comment`,`datetime`,`hidden` FROM `t_comments` WHERE `hidden` IS NULL ";
	
	// For a place (default: all)
	if($id !== false && is_numeric($id)) $query .= "AND `fk_place` = ".mysql_real_escape_string($id);
	
	// Query with limit
	if($limit !== false && !empty($limit)) $query .= " LIMIT ".mysql_real_escape_string($limit);
	
	$query .= " ORDER BY `datetime` ASC";
	
	// Build an array
   	$res = mysql_query($query);
   	
   	$i=0;
	while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
   	    $result[$i]["id"] = $r["id"];
   	    
   	    if($id === false) $result[$i]["place_id"] = $r["fk_place"];
   	    
   	    $result[$i]["comment"] = stripslashes($r["comment"]);
   	    $result[$i]["datetime"] = $r["datetime"];
   	    
   	    // User stuff
   	    if(!empty($r["fk_user"])) $result[$i]["user"]["id"] = $r["fk_user"];
   	    
   	    if(!empty($r["fk_user"])) $result[$i]["user"]["name"] = username($r["fk_user"]);
   	    
   	    if(!empty($r["nick"])) $result[$i]["user"]["nick"] = $r["nick"];
   	    
   	    $i++;
   	}
   	
   	return $result;
}



/* 
 * List available countries with markers
 * type: option | tr | li | array (default)
 * order: markers | name (default) | false
 * limit: int | false (default)
 * count: true (default) | false 
 * world: true | false (default) (list's all the countries, even without any markers)
 * coordinates: true | false (default)
 */
function list_countries($type="array", $order="name", $limit=false, $count=true, $world=false, $coordinates=false, $selected_country=false) {
	start_sql();

	// Get all country iso-codes
	$codes = countrycodes();
	
	// Get also coordinates
	if($coordinates==true) $country_coordinates = country_coordinates();
	
	if($world==true) $empty_countries = $codes;
	
	
	// Build up a query
	$query = "SELECT `country`, count(*) AS cnt
	                    FROM `t_points`
	                    WHERE `type` = 1
	                    GROUP BY `country`";
	
	
	if($order=="markers") $query .= " ORDER BY cnt DESC";
	elseif($order=="name") $query .= " ORDER BY country ASC";
	
	
	// Gathering stuff...
	$res = mysql_query($query);

	// Create an array out of this stuff
	$i=0;
	while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
		
		// $r['country'] contains ISO-code of the country, Eg. RU for Russia
	
		// Remove "used" country from empty countries -list
		if($world==true) unset($empty_countries[$r['country']]);
	
		// Get translated countryname
		$countryname = ISO_to_country($r['country'], $codes);
	
		// Gather an array
		$country_array[$countryname]["iso"] = $r['country'];
		$country_array[$countryname]["name"] = $countryname;
		$country_array[$countryname]["places"] = $r['cnt'];
		
		// Add also coordinates if requested
		if($coordinates==true && $country_coordinates[$r['country']]["lat"] != "" && $country_coordinates[$r['country']]["lon"] != "") {
			$country_array[$countryname]["lat"] = $country_coordinates[$r['country']]["lat"];
			$country_array[$countryname]["lon"] = $country_coordinates[$r['country']]["lon"];
		} elseif($coordinates==true) {
			$country_array[$countryname]["lat"] = "";
			$country_array[$countryname]["lon"] = "";
		}
		
		// limit results if asked to
		if($limit!=false && $i==$limit) break;
		$i++;
	}
	
	
	// Add empty countries to the main list if requested
	if($world==true) {
		foreach($empty_countries as $iso => $countryname) {
			$country_array2[$countryname]["iso"] = $iso;
			$country_array2[$countryname]["name"] = $countryname;
			$country_array2[$countryname]["places"] = 0;
			
			// Add also coordinates if requested
			if($coordinates==true && $country_coordinates[$iso]["lat"] != "" && $country_coordinates[$iso]["lon"] != "") {
				$country_array2[$countryname]["lat"] = $country_coordinates[$iso]["lat"];
				$country_array2[$countryname]["lon"] = $country_coordinates[$iso]["lon"];
			} elseif($coordinates==true) {
				$country_array[$countryname]["lat"] = "";
				$country_array[$countryname]["lon"] = "";
			}
		}
	
		$country_array = array_merge($country_array, $country_array2);
		//sort($country_array);
	}
	
	// Alphabetic order by translated countrynames
	if($order=="name") ksort($country_array);
	
	
	// Print it out
	foreach($country_array as $country) {
	
		// print a selection option
		if($type=="option") {
			echo '<option ';
			if($selected_country == $country["iso"]) echo 'selected="selected" ';
			echo 'value="'.$country["iso"].'" class="'.strtolower($country["iso"]).'">'.$country["name"];
			if($count==true) echo ' <small class="grey">('.$country["places"].')</small>';
			echo '</option>';
		}
		
		// print a list item
		elseif($type=="li") {
			echo '<li><img class="flag" alt="'.strtolower($country["iso"]).'" src="static/gfx/flags/'.strtolower($country["iso"]).'.png" /> <a href="./?q='.urlencode($country["name"]).'" id="search_for_this">'.$country["name"]."</a>";
			if($count==true) echo ' <small class="grey">('.$country["places"].')</small>';
			echo '</li>';
		}
		
		// print a table row
		elseif($type=="tr") {
			echo '<tr><td><img class="flag" alt="'.strtolower($country["iso"]).'" src="static/gfx/flags/'.strtolower($country["iso"]).'.png" /> <a href="./?q='.urlencode($country["name"]).'" id="search_for_this">'.$country["name"].'</a></td>';
			if($count==true) echo '<td>'.$country["places"].'</td>';
			echo '</tr>';
		}
		
	}
	
	// Attach search function to cities for li/tr -lists
	if($type=="li" OR $type=="tr") {
	?>
	<script type="text/javascript">
	    $("a#search_for_this").click(function(e){
	    	e.preventDefault();
	    	search($(this).text(),true);
	    });
	</script>
	<?php
	}
	
	// Return gathered array if requested type = array 
	if($type=="array") return $country_array;

}



/* 
 * List available cities with markers
 * type: option | tr | li | array (default)
 * order: markers (default) | name (TODO!)
 * limit: int | false (default)
 * count: true (default) | false 
 * country: ISO-countrycode | false (default)
 * user_id: INT | false (default)
 */
function list_cities($type="array", $order="markers", $limit=false, $count=true, $country=false, $user_id=false) {
	start_sql();
	
	// Get ISO-countrycode list with countrynames
	$codes = countrycodes();
	
	// Start building a query
	$query = "SELECT country, locality, count(*) AS cnt FROM `t_points` WHERE `type` = 1 AND `locality` IS NOT NULL";
	
	// Only from some specific country
	if($country != false && strlen($country) == 2) {
		$query .= " AND country = '".mysql_real_escape_string($country)."'";
	} 
	else {
		$country = false;
	}
	
	// Only from some specific user
	if($user_id != false && is_numeric($user_id)) {
		$query .= " AND user = '".mysql_real_escape_string($user_id)."'";
	} 
	else {
		$user_id = false;
	}
	
	
	// Continue with query...
	$query .= " GROUP BY country, locality ORDER BY cnt DESC";
	

    $res = mysql_query($query);

	$i=0;
	while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
		/* 
		 * $r[#]:
		 * 0 = countrycode
		 * 1 = locality
		 * 2 = markercount
		 */

		$countryname = ISO_to_country($r['country'], $codes);
	
	
		if($type=="option") {
			echo '<option value="'.$r['locality'].'" class="'.strtolower($r['country']).'">'.$r['locality'];
			
			if($country != false) echo ', '.$countryname;
			
			if($count==true) echo ' ('.$r['cnt'].')';
			
			echo '</option>';
		}
		elseif($type=="li") {
		
			if($country == false) echo '<li><img class="flag" alt="'.strtolower($r['country']).'" src="static/gfx/flags/'.strtolower($r['country']).'.png" /> <a href="./?q='.urlencode($r['locality'].', '.$countryname).'" id="search_for_this">'.$r['locality'].', '.$countryname.'</a>';
			else echo '<li><a href="./?q='.urlencode($r['locality']).'" id="search_for_this">'.$r['locality'].'</a>';
			
			if($count==true) echo ' <small class="grey">('.$r['cnt'].')</small>';
			
			echo '</li>';
		}
		elseif($type=="tr") {
			echo '<tr><td><a href="./?q='.urlencode($r['locality']).'" id="search_for_this">'.$r['locality'].'</a></td>';
			
			if($country == false) echo '<td><img class="flag" alt="'.strtolower($r['country']).'" src="static/gfx/flags/'.strtolower($r['country']).'.png" /> <a href="./?q='.urlencode($countryname).'" id="search_for_this">'.$countryname.'</a></td>';
			
			if($count == true) echo '<td>'.$r['cnt'].'</td>';
			
			echo '</tr>';
		}
		else {
			$array[$i]["locality"] = $r['locality'];
			if($country == false) {
				$array[$i]["country_iso"] = $r['country'];
				$array[$i]["country_name"] = $countryname;
			}
			$array[$i]["places"] = $r['cnt'];
		}
		
		
		if($limit!=false && $i==$limit) break;
		$i++;
	}
	
	// Attach search function to cities for li/tr -lists
	if($type=="li" OR $type=="tr") {
	?>
	<script type="text/javascript">
	    $("a#search_for_this").click(function(e){
	    	e.preventDefault();
	    	search($(this).text(),true);
	    });
	</script>
	<?php
	}

	// Return gathered array if any
	if(isset($array)) return $array;
}



/* 
 * List all continents
 * type: option | tr | li | array (default)
 * count: true | false (default)
 */
function list_continents($type="array", $count=false) {

	// Continents (translated)
	$continents["AS"]["name"] = _("Asia");
	$continents["AS"]["code"] = "AS";
	$continents["AS"]["places"] = "0";

	$continents["AF"]["name"] = _("Africa");
	$continents["AF"]["code"] = "AF";
	$continents["AF"]["places"] = "0";

	$continents["NA"]["name"] = _("North America");
	$continents["NA"]["code"] = "NA";
	$continents["NA"]["places"] = "0";

	$continents["SA"]["name"] = _("South America");
	$continents["SA"]["code"] = "SA";
	$continents["SA"]["places"] = "0";

	$continents["AN"]["name"] = _("Antarctica");
	$continents["AN"]["code"] = "AN";
	$continents["AN"]["places"] = "0";

	$continents["EU"]["name"] = _("Europe");
	$continents["EU"]["code"] = "EU";
	$continents["EU"]["places"] = "0";

	$continents["OC"]["name"] = _("Australia and Oceania");
	$continents["OC"]["code"] = "OC";
	$continents["OC"]["places"] = "0";

	// Get marker count if requested
	if($count==true) {
		
		start_sql();
		
		$query = "SELECT `continent`, count(*) AS cnt
	                    FROM `t_points`
	                    WHERE `type` = 1
	                    GROUP BY `continent`  ORDER BY cnt DESC";
	
    	$res = mysql_query($query);
		
		while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
			$continents[$r["continent"]]["places"] = $r["cnt"];
		}
	}
	


	// Spread it out
	if($type == "option") {
		foreach($continents as $continent) {
			echo '<option value="'.$continent["code"].'">'.$continent["name"];
			
			if($count==true) echo " (".$continent["places"].")";
			
			echo "</option>\n";
		}
	}
	elseif($type == "li") {
		foreach($continents as $continent) {
			echo "<li>".$continent["name"];
			
			if($count==true) echo " (".$continent["places"].")";
			
			echo "</li>\n";
		}
	}
	elseif($type == "tr") {
		foreach($continents as $continent) {
			echo "<tr><td>".$continent["name"]."</td>";
			
			if($count==true) echo "<td>".$continent["places"]."</td>";
			
			echo "</tr>\n";
		}
	}
	else {		
		return $continents;
	}
}


/* 
 * Places in total
 * country: ISO shortcode for the country | false (default; will just get them all)
 */
function total_places($country=false) {

	// Start building a query
	$query = "SELECT COUNT(id) FROM t_points WHERE `type` = 1";

	// Query just from one country
	if($country != false && strlen($_GET["country"]) == 2) $query .= " AND country = '".$country."'";

	// Gather data
	start_sql();
	$result = mysql_query($query);
	if (!$result) {
	   die("query failed.");
	}

	// Plop!
	while ($row = mysql_fetch_array($result)) {
	    return $row[0];
	}
}

function country_info($iso=false, $lang=false) {
    global $settings;

    // Validate ISO country code
    $codes = countrycodes();
    if($iso===false OR strlen($iso) != 2 OR !isset($codes[strtoupper($iso)])) return false;;
    
    // Validate language		
    if($lang===false OR empty($lang) OR !isset($settings["valid_languages"][$lang])) $lang = $settings["language"]; 

	// Build a query
	$query = "SELECT `iso`,`".mysql_real_escape_string($lang)."`,`lat`,`lon` FROM `t_countries` WHERE `iso` = '".mysql_real_escape_string(strtoupper($iso))."' LIMIT 1";

    // Build an array
	$res = mysql_query($query);
	if(!$res) return false;
	$i=0;
    while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
	    $result["iso"] = $r["iso"];
	    $result["name"] = $r[$lang];
	    $result["lat"] = $r["lat"];
	    $result["lon"] = $r["lon"];
	    $i++;
	}

	// Return
	return $result;
}

/* 
 * Get countrycode list in two forms:
 * code => countryname (default)
 * or
 * countryname => code
 *
 * first: code | name
 * lang: get countrynames from different languagecol: en_UK | fi_FI | de_DE | es_ES | ru_RU | lt_LT | ...etc
 * lowercase: true | false (default)  - returns names in lowercase
 */
function countrycodes($first="code", $lang="", $lowercase=false, $one_try = false) {
	global $settings;

	// Check if language is valid (if not, use default)
	// Settings comes from config.php
	if(!isset($settings["valid_languages"][$lang])) $lang = $settings["language"];


	// Built up a query
	$query = "SELECT iso, ".mysql_real_escape_string($lang);
	
	// Get default language name also, if query language wasn't already it (we use it as a fall-back name)
	// Most likely it's en_UK
	if($lang != $settings["default_language"]) $query .= ", ".mysql_real_escape_string($settings["default_language"]);
	
	$query .= " FROM `t_countries`";


	// Gather data
	start_sql();
	$result = mysql_query($query);

	if(!$result) {
		// No result with that language
		// Get listing with default language
		if($one_try === false) {
			countrycodes($first, $settings["default_language"], $lowercase, true);
		}
		else {
			echo " <!-- ERROR: SQL query failed with countrycodes() --> ";
			@include("../maintenance_page.php");
			die();
		}
	}
	// Got result, continue...
	else {
	
		while ($row = mysql_fetch_array($result)) {
		    
		    // Countryname (fall-back to the default)
		    if(!empty($row[$lang])) $name = $row[$lang];
		    else $name = $row[$settings["default_language"]];
		    
		    // Make name lowercase if asked to
		    if($lowercase==true) $name = strtolower($name);
		
		    // Gather list in form "iso => name" or "name => iso"
		    if($first=="name") $list[$name] = $row["iso"];
		    else $list[$row["iso"]] = $name;
		}
	
	}
	
	return $list;
}



/* 
 * List countrycoordinates in array:
 * Array
 * (
 *     [iso] 	=>	 "de"
 *     [lat] 	=>	 51
 *     [lon] 	=>	 9
 * )
 
 *
 */
function country_coordinates() {

	// Gather data
	start_sql();
	$result = mysql_query("SELECT iso, lat, lon FROM `t_countries`");
	if (!$result) {
	   die("Error: SQL query failed with country_coordinates()");
	}
	while ($row = mysql_fetch_array($result)) {
		
	    $list[$row["iso"]]["iso"] = $row["iso"];
	    $list[$row["iso"]]["lat"] = $row["lat"];
	    $list[$row["iso"]]["lon"] = $row["lon"];
	}
	
	return $list;
}


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
 * Produce an URL to image map
 * Requires: 
 * - lat
 * - lon
 *
 * Optional:
 * - zoom
 * - format (png|jpg)
 * - width
 * - height
 *
 * returns an url to the image from openstreetmap
 * e.g. http://tah.openstreetmap.org/MapOf/?lat=62&long=23&z=13&w=500&h=500&skip_attr=on&format=jpeg
 */
function image_map($lat, $lon, $zoom=15, $format='png', $width=150, $height=150) {

	if(!validate_lon($lon) OR !validate_lat($lat) OR $zoom===false OR $zoom < 0 OR $width <= 0 OR $height <= 0) 
	  return false;

	elseif($format != 'png' && $format != 'jpeg') 
	  return false;

	else 
	  return 'http://tah.openstreetmap.org/MapOf/?lat='.urlencode($lat).'&long='.urlencode($lon).'&z='.urlencode($zoom).'&w='.urlencode($width).'&h='.urlencode($height).'&skip_attr=on&format='.urlencode($format);

}



/* 
 * Return a user name by ID
 */
function username($id, $link=false) {

	if(!empty($id) && is_numeric($id)) {
		start_sql();
		
		// Get users name from database
		$res = mysql_query("SELECT `id`,`name` FROM `t_users` WHERE `id` = ".mysql_real_escape_string($id)." LIMIT 1");
		if(!$res) return _("Anonymous");
		
		// If we have a result, go and get the name
		if(mysql_num_rows($res) > 0) {
		    while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
		    
		    	if($link===true) return '<a href="./?page=profile&amp;user_id='.$id.'" onclick="open_page(\'profile\', \'user_id='.$id.'\'); return false;" title="'._("Profile").'">'.htmlspecialchars($r["name"]).'</a>';
		    	else return htmlspecialchars($r["name"]);
		    }
		}
		else return _("Anonymous");
	}
	else return _("Anonymous");
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
 * Returns a graph <table class="chart">
 * CSS can be found from static/css/main.css
 * size: small | big
 */
function rating_chart_html($rating_stats=false, $width='100%', $size='small') {
	global $settings;
	
	// Test so that we have a rating stats in an array form
	if(!is_array($rating_stats)) return false;

	// Default is 0%
	$raintg_percentages[1]["rating"] = "0";
	$raintg_percentages[1]["count"] = "0";
	$raintg_percentages[2]["rating"] = "0";
	$raintg_percentages[2]["count"] = "0";
	$raintg_percentages[3]["rating"] = "0";
	$raintg_percentages[3]["count"] = "0";
	$raintg_percentages[4]["rating"] = "0";
	$raintg_percentages[4]["count"] = "0";
	$raintg_percentages[5]["rating"] = "0";
	$raintg_percentages[5]["count"] = "0";


	// Count percentages
	foreach($rating_stats["ratings"] as $rating) {
		// Count the percentage of this rating
		$raintg_percentages[$rating["rating"]]["rating"] = 100*($rating["rating_count"]/$rating_stats["rating_count"]);
		$raintg_percentages[$rating["rating"]]["count"] = $rating["rating_count"];
	}

	// Produce HTML
	$chart = '<table cellpadding="0" cellspacing="0" style="width: '.htmlspecialchars($width).';" class="chart light ';
	$chart .= ($size == 'big') ? "bigger": "smaller";
	$chart .= '">';
	$chart .= '<tbody>';
	
	for($i=1; $i <= 5; $i++) {
	
		$chart .= '<tr>
			<td class="label">'.str_replace(" ", "&nbsp;",hitchability2textual($i)).'</td>
			<td class="bar"><span style="width:'.round($raintg_percentages[$i]["rating"]).'%; background-color: #'.$settings["hitchability_colors"][$i].';"></span></td>
			<td class="value">'.$raintg_percentages[$i]["count"].'</td>
		</tr>';
	
	}
	
	$chart .= '</tbody></table>';

	return $chart;
}



/*
 * Returns a graph img-url of ratings
 * Note: this is being replaced by our own HTML based chart, see rating_chart_html()
 * Uses Google Chart API
 * http://code.google.com/apis/chart/docs/gallery/bar_charts.html
 */
function rating_chart($rating_stats=false, $width="50") {
	global $settings;

	// Get ALL ratings
	if($place===false) {
	
	}
	// Test so that we have a rating stats in an array form
	elseif(!is_array($rating_stats)) return false;
	
	// Validate width
	if(empty($width) || !is_numeric($width)) $width = "50";

	// Default is 0%
	$raintg_percentages[1]["rating"] = "0";
	$raintg_percentages[1]["count"] = "0";
	$raintg_percentages[2]["rating"] = "0";
	$raintg_percentages[2]["count"] = "0";
	$raintg_percentages[3]["rating"] = "0";
	$raintg_percentages[3]["count"] = "0";
	$raintg_percentages[4]["rating"] = "0";
	$raintg_percentages[4]["count"] = "0";
	$raintg_percentages[5]["rating"] = "0";
	$raintg_percentages[5]["count"] = "0";

	// Count percentages
	foreach($rating_stats["ratings"] as $rating) {
		// Count the percentage of this rating
		$raintg_percentages[$rating["rating"]]["rating"] = 100*($rating["rating_count"]/$rating_stats["rating_count"]);
		$raintg_percentages[$rating["rating"]]["count"] = $rating["rating_count"];
	}

	$url = 'http://chart.apis.google.com/chart';
	
	$url .= '?cht=bhs';
	$url .= '&chf=bg,s,faf9f3';
	$url .= '&chs='.$width.'x55';
	$url .= '&chd=t:'.$raintg_percentages[1]["rating"].','.$raintg_percentages[2]["rating"].','.$raintg_percentages[3]["rating"].','.$raintg_percentages[4]["rating"].','.$raintg_percentages[5]["rating"];
	$url .= '&chxt=y,r';
	$url .= '&chxl=';
		$url .= '1:';
		$url .= '|'.hitchability2textual(5);
		$url .= '|'.hitchability2textual(4);
		$url .= '|'.hitchability2textual(3);
		$url .= '|'.hitchability2textual(2);
		$url .= '|'.hitchability2textual(1);
		$url .= '|';
		
		$url .= '0:';
		$url .= '|'.$raintg_percentages[5]["count"];
		$url .= '|'.$raintg_percentages[4]["count"];
		$url .= '|'.$raintg_percentages[3]["count"];
		$url .= '|'.$raintg_percentages[2]["count"];
		$url .= '|'.$raintg_percentages[1]["count"];
		$url .= '|';
	#$url .= '&chxs=0,ad8c55,8|1,ad8c55,7';
	$url .= '&chxs=1,ad8c55,10,-1,t,ad8c55|0,ad8c55,10';
	
	$url .= '&chco='.$settings["hitchability_colors"][1].'|'.$settings["hitchability_colors"][2].'|'.$settings["hitchability_colors"][3].'|'.$settings["hitchability_colors"][4].'|'.$settings["hitchability_colors"][5].'';
	$url .= '&chbh=6,3';


	return $url;
}


/* 
 * Return hitchability votes in total (amount)
 */
function hitchability_votes_total() {
	start_sql();
	$result = mysql_query("SELECT COUNT(id) as count FROM `t_ratings` WHERE `rating` IS NOT NULL AND `rating` != '0'");
    while ($row = mysql_fetch_array($result)) {
    	return $row["count"];
    	break;
    }
}



/* 
 * Check if nick is available and ok in other ways too
 */
function available_nick($nick=false) {
	
	// Pre non allowed nicks (keep them lowercase)
	$taken_nicks = array(
		"anonymoys",
		"admin",
		"administrator",
		"unknown",
		"nickname",
		"nick",
		"name",
		"hitchwiki",
		"hitchwiki_maps"
	);

	// Check if nick is ok and return
	if(strlen(trim($nick)) <= 3 OR strlen(trim($nick)) > 255 OR empty($nick) OR in_array(strtolower($nick), $taken_nicks)) return false;
	else return true;
}



/* 
 * Return info about logged in user
 * or if user isn't logged in
 */
function current_user($get_password=false) {
	/*
	global $_COOKIE,$settings;
	
	$cookie_email = $settings["cookie_prefix"]."email";
	$cookie_password = $settings["cookie_prefix"]."password";

	if(isset($_COOKIE[$cookie_email]) && isset($_COOKIE[$cookie_password])) {
		$user = check_login($_COOKIE[$cookie_email], $_COOKIE[$cookie_password],$get_password);
		
		// Will either return an array including userinfo or false in case of login fails (wrong email/password)
		// see check_login() for more details
		return $user;
	}
	else return false;
	*/
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
			$user["google_latitude"] = $r["google_latitude"];
			$user["centered_glatitude"] = $r["centered_glatitude"];
			$user["allow_gravatar"] = $r["allow_gravatar"];
			$user["map_google"] = $r["map_google"];
			$user["map_yahoo"] = $r["map_yahoo"];
			$user["map_vearth"] = $r["map_vearth"];
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
	start_sql();

	$res = mysql_query("SELECT * FROM `t_users` WHERE `id` = '".mysql_real_escape_string($session["wsUserID"])."' LIMIT 1");
   	
   	if(!$res) return false;
			
	// If we have a result, continue gathering user array
	if(mysql_num_rows($res) > 0) {

		$last_seen = mysql_query("UPDATE `t_users` SET `last_seen` = NOW() WHERE `id` = ".mysql_real_escape_string($session["wsUserID"])." LIMIT 1");

		while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {

			$user["logged_in"] = true;
			$user["id"] = $session["wsUserID"];
			$user["name"] = $session["wsUserName"];
			$user["location"] = $r["location"];
			$user["country"] = $r["country"];
			$user["language"] = $r["language"];
			$user["registered"] = $r["registered"];
			$user["last_seen"] = $r["last_seen"];
			$user["private_location"] = $r["private_location"];
			$user["google_latitude"] = $r["google_latitude"];
			$user["centered_glatitude"] = $r["centered_glatitude"];
			$user["allow_gravatar"] = $r["allow_gravatar"];
			$user["map_google"] = $r["map_google"];
			$user["map_yahoo"] = $r["map_yahoo"];
			$user["map_vearth"] = $r["map_vearth"];
			$user["map_default_layer"] = $r["map_default_layer"];
			
			// Admin?
			if($r["admin"]=="1" && $settings["allow_admins"] === true) $user["admin"] = true;
			else $user["admin"] = false;
			
			// If the name in the session was different than the one in DB, update DB
			if($r["name"] != $session["wsUserName"]) {
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

		$mw_res = mysql_query("SELECT `user_id`,`user_name`,`user_email`,`user_email` FROM `".$mysql_conf["mediawiki_db"]."`.`user` WHERE user_id = ".mysql_real_escape_string($session["wsUserID"])." LIMIT 1");

		if(mysql_num_rows($mw_res) > 0) {
			while($mw_r = mysql_fetch_array($mw_res, MYSQL_ASSOC)) {
			    $email = "'".$mw_r["user_email"]."'";
			}
		}
		else $email = "NULL";
		
	
		/*
		 * Add new user to the Maps DB
		 */
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
				
		$res = mysql_query($query);
		   
		if(!$res) return false;
		else return get_user($session);
	
	}

}


/* 
 * Protect email against spam
 */
function protect_email($email) {
	return str_replace("@", "&#64;", $email);
}


/*
 * Print out an error sign
 */
function error_sign($msg=false, $hide=true) {

	$random = rand(0,1000);
	
	$title = _("Error");
	if(!empty($msg)) {
		$title .= ":";
		$msg = htmlspecialchars($msg);
	} else $msg = "";
	
	// Print error sign
	echo '<div class="ui-state-error ui-corner-all" style="padding: 0 .7em; margin: 10px 0;" id="error_'.$random.'">'. 
	    '<p><span class="ui-icon ui-icon-alert" style="float: left; margin-right: .3em;"></span> '.
	    '<strong>'.$title.'</strong> <span class="error_text">'.$msg.'</span></p>'.
	    '</div>';
	
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

	$random = rand(0,1000);
	
	if(!empty($msg)) {
	
		// Print info sign
		echo '<div class="ui-state-highlight ui-corner-all" style="padding: 0 .7em; margin: 20px 0;" id="info_'.$random.'">'. 
		    '<p><span class="ui-icon ui-icon-info" style="float: left; margin-right: .3em;"></span>  '.
		    '<span class="info_text">'.htmlspecialchars($msg).'</span></p>'.
		    '</div>';
		
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
 * Gives an elevation in meters
 *
 * http://www.geonames.org/export/web-services.html
 * Elevation - Aster Global Digital Elevation Model
 * sample area: ca 30m x 30m, between 83N and 65S latitude. Result : a single number giving the elevation in meters 
 * according to aster gdem, ocean areas have been masked as "no data" and have been assigned a value of -9999"
 */
function get_elevation($lat,$lon) {

	$elevation = readURL("http://ws.geonames.org/astergdem?lat=".urlencode($lat)."&lng=".urlencode($lon));

	if(trim($elevation) == '-9999') return '0';
	elseif(!empty($elevation)) return trim($elevation);
	else return false;
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



/*
 * Public transportation functions
 * * * * * * * * * * * * * * * * *
 */
 
/*
 * List public transportation types
 */
function pt_types() {
	return array(
		0 => _("Other"),
		1 => _("Local bus"),
		2 => _("Trolleybus"),
		3 => _("Tram"),
		4 => _("Metro"),
		5 => _("Commuter train"),
		6 => _("Taxi"),
		7 => _("Long distance bus"),
		8 => _("Long distance train"),
		9 => _("Airline"),
		10 => _("Shipping"),
		11 => _("Carsharing"),
		12 => _("Car rental")
	);
}

 
/* 
 * Print out type
 * type: INT
 * output: text | image | icon_text
 */
function pt_type($type, $output="text") {
	global $settings;
	
	$types = pt_types();
	
	// Image
	if($output == "image") return '<img src="'.$settings["base_url"].'/static/gfx/transportation_'.htmlspecialchars($type).'.png" class="pt_type png" alt="'.$types[$type].'" />';

	// Plain text + image icon
	if($output == "icon_text") return '<span class="icon transportation_'.$type.'">'.$types[$type].'</span>';

	// Plain text
	else return $types[$type];
		
}


/* 
 * Print out the list of publics in certain country
 */
function pt_list($country_iso) {
	
	$user = current_user();
	
	// Built up a query
	$query = "SELECT * FROM `t_ptransport` WHERE `country` = '".mysql_real_escape_string($country_iso)."' ORDER BY `city`,`type` ASC";
	
	// Gather data
	start_sql();
	$result = mysql_query($query);
	if (!$result) {
	   die("Error: SQL query failed.");
	}
	
	// If some results, print out
	if(mysql_num_rows($result) >= 1) {
?>
		<table class="infotable" id="public_transport_catalog" cellspacing="0" cellpadding="0">
			<thead>
				<tr>
					<th><?php echo _("City"); ?></th>
					<th><?php echo _("Site"); ?></th>
					<th><?php echo _("Type"); ?></th>
					<?php if($user["admin"]===true): ?>
					<th><?php echo _("Manage"); ?></th>
					<?php endif; ?>
				</tr>
			</thead>
		    <tbody>
		    		<?php
		    		
						// Print out page rows
						while ($row = mysql_fetch_array($result)) {
							
							echo '<tr valign="top">';
							
							// City
							if(!empty($row["city"])) echo '<td>'.htmlspecialchars($row["city"]).'</td>';
							else echo '<td> </td>';
							
							// URL
							if(!empty($row["title"])) echo '<td><a href="'.htmlspecialchars($row["URL"]).'" rel="nofollow" target="_blank">'.htmlspecialchars($row["title"]).'</a></td>';
							else echo '<td><a href="'.htmlspecialchars($row["URL"]).'" rel="nofollow" target="_blank">'._("Go to site").'</a></td>';
							
							// Type
							echo '<td class="pt_types">';
							if(strstr($row["type"], ";")) {
								foreach(explode(";", $row["type"]) as $type) {
									echo '<small>'.pt_type($type, 'icon_text').'</small><br />';
								}
							}
							elseif($row["type"] != "") {
								echo '<small>'.pt_type($row["type"], 'icon_text').'</small>';
							}
							echo ' </td>';
							
							// Manage -col for admins
							if($user["admin"]===true) {
								?>
								<td>
							 	<a href="admin/?page=public_transport&amp;remove=<?php echo $row["id"]; ?>" class="remove_page ui-icon ui-icon-trash align_right" title="<?php echo _("Remove page permanently"); ?>"></a>
							 	<a href="admin/?page=public_transport&amp;edit=<?php echo $row["id"]; ?>" class="ui-icon ui-icon-pencil align_right" title="<?php echo _("Edit page"); ?>"></a>
							 	</td>
							 	<?php
							}
							
							echo '</tr>';
						}
					?>
		    </tbody>
		</table>
		
		<?php if($user["admin"]===true): ?>
		<script type="text/javascript">
		$(function() {
			
			// Confirm delete
			$("#public_transport_catalog .remove_page").click(function(e){
				e.preventDefault();
				
				if(confirm('<?php echo _("Are you sure?"); ?>')) {
					$(location).attr('href', $(this).attr("href"));
				}
			});
		
		});
		</script>
		<?php endif; ?>
		
		<br />
		<small class="icon transportation_in-city"><?php echo _("In-city transportation"); ?></small><br />
		<small class="icon transportation_inter-city"><?php echo _("Inter-city / international transportation"); ?></small><br />
<?php
	}
	else {
		?>
		<p><?php echo _("No public transport found for this country."); ?> <a href="./?page=add_public_transport" onclick="open_page('add_public_transport'); return false;"><?php echo _("Add some?"); ?></a></p>
		<?php
	}
}


?>