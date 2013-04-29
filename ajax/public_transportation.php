<?php
/*
 * Hitchwiki Maps: public_transport.php
 * List public transportation webpages
 */

/*
 * Load config to set language and stuff
 */
require_once("../config.php");


/* 
 * Give names behind ISO-country codes
 * FI -> Finland, DE -> Germany, etc
 */
if(!function_exists("ISO_to_country")):
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
endif;

/* 
 * Gather data
 */
if(isset($_GET["country"]) && strlen($_GET["country"]) == 2) {

	$country["iso"] = 			htmlspecialchars(strtoupper($_GET["country"]));
	$country["name"] = 			ISO_to_country($country["iso"]);

}
else {
	error_sign("Choose a country.", false);
	exit;
}


/* 
 * Print it out:
 */
?>
	
	<h3><img class="flag" alt="<?php echo $country["iso"]; ?>" src="<?= $settings["base_url"]; ?>/static/gfx/flags/<?php echo strtolower($country["iso"]); ?>.png" /> <?php echo $country["name"]; ?></h3>
	
	<?php pt_list($country["iso"]); ?>
