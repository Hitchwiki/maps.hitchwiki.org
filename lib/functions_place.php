<?php
/* Hitchwiki - maps
 * Hitchhiking place related functions
 * - get_place()
 * - rating_stats()
 * - waitingtimes()
 * - get_comments()
 */


/*
 * Get a place array by ID
 * id: INT (required)
 * wide: true | false (default) - gets more info than just basics
 */
function get_place($id=false, $more=false, $counter=false) {
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
 * Returns nice placename with optional link
 */
function place_name($place_id, $link=false) {

	$place = get_place($place_id, true);

	if($place !== false) {
	
		if($link) $return .= '<a href="'.$place["link"].'" onclick="open_place('.$place["id"].'); return false;">';

		if(!empty($place["location"]["locality"])) $return .= $place["location"]["locality"];
		
		if(!empty($place["location"]["locality"]) && !empty($place["location"]["country"]["name"])) $return .= ', ';
		
		if(!empty($place["location"]["country"]["name"])) $return .= $place["location"]["country"]["name"];
		
		if($link) $return .= '</a>';
		
		return $return;
	
	}
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

	$result = [];


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





?>
