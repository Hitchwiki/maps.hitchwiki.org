<?php
/*
 * Hitchwiki Maps: opensearch/suggestions.php
 * Outputs suggestions list in opensearch suggestions json format
 * 
 * http://www.opensearch.org/Specifications/OpenSearch/Extensions/Suggestions/1.0
 */

/*
 * Load config
 */
require_once "../config.php";

#header ("content-type: text/xml");

/* An example answer would be: 
 [
 	"sea",
 	[
 		"sears",
 		"search engines",
 		"search engine",
 		"search",
 		"sears.com",
 		"seattle times"
 	],
 	[
 		"7,390,000 results",
 		"17,900,000 results",
 		"25,700,000 results",
 		"1,220,000,000 results",
 		"1 result",
 		"17,600,000 results"
 	],
 	[
 		"http://example.com?q=sears",
 		"http://example.com?q=search+engines",
 		"http://example.com?q=search+engine",
 		"http://example.com?q=search",
 		"http://example.com?q=sears.com",
 		"http://example.com?q=seattle+times"
 	]
 ]
*/
$q = trim(htmlspecialchars(strip_tags($_GET["q"])));
$q = ( !empty($q) ) ? $q : false;

if($q) {

	// Start json
	$json = '[';
	
	// Search term
	$json .= '"'.addslashes($q).'",';
	
	// Language
	$lang = (isset($_GET["lang"]) && !empty($_GET["lang"])) ? strip_tags($_GET["lang"]) : $settings["language"];

	start_sql();
	
	
	// Start building a query
	$query = "SELECT country, locality, count(*) AS cnt 
				FROM `t_points` 
				WHERE `locality` LIKE '" . mysql_real_escape_string($q) . "%' AND `type` = 1 AND `locality` IS NOT NULL 
				GROUP BY country, locality 
				ORDER BY cnt DESC
				LIMIT 10";

    $res = mysql_query($query);

	// Get ISO-countrycode list with countrynames
	#$codes = countrycodes();

	while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {

		#$countryname = ISO_to_country($r['country'], $codes);
		$countryname = ISO_to_country($r['country']);

		$suggestion_terms .= '"'.$r['locality'].', '.$countryname.'",';
			
		$suggestion_results .= '"'.sprintf(ngettext("%d result", "%d results", $r['cnt']), $r['cnt']).'",';
			
		$suggestion_urls .= '"'.$settings["base_url"].'/?src=os&amp;lang='.urlencode($lang).'&amp;q='.urlencode($r['locality'].', '.$countryname).'",';
	}
	
	// Print results
	if(!empty($suggestion_terms)) {
	
		// Fix last "," away
		$suggestion_terms = substr($suggestion_terms, 0, -1);
		$suggestion_results = substr($suggestion_results, 0, -1);
		$suggestion_urls = substr($suggestion_urls, 0, -1);
	
		// Output suggestions
		$json .= '['.$suggestion_terms.'],';
		$json .= '['.$suggestion_results.'],';
		$json .= '['.$suggestion_urls.']';
	}
	
	$json .= ']'; // end of json

	echo $json;

} // !empty q
else {

	echo '[]';

}
	
?>