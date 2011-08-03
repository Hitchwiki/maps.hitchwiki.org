<?php
/* Hitchwiki - maps
 * Lists and statistical functions
 * - list_countries()
 * - list_cities()
 * - list_continents()
 * - total_places()
 * - country_info()
 * - countrycodes()
 * - country_coordinates()
 * - hitchability_votes_total()
 * - rating_chart()
 * - rating_chart_html()
 * - hitchability_votes_total()
 */


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


?>