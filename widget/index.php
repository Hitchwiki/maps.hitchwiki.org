<?php
/*
 * Initialize Maps
 */
if(@is_file('../config.php')) require_once "../config.php";
else { $settings["maintenance_page"] = true; $settings["non_maintenance_ip"] = array(); }


/*
 * Put up a maintenance -sign
 * Set it up from config.php or test it from ./?maintenance
 */
if(isset($_GET["maintenance"])) $settings["maintenance_page"] = true;
if($settings["maintenance_page"]===true && !in_array($_SERVER['REMOTE_ADDR'], $settings["non_maintenance_ip"])) {

?><!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" dir="ltr" lang="en">
	<head profile="http://gmpg.org/xfn/11">
		<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
		<title>Hitchwiki - Maps</title>
        <base href="../" />
        <link rel="stylesheet" type="text/css" href="static/css/widget.css" media="all" />
	</head>
	<body>
		<div style="padding:30px;">
			<em>Sorry, Embedding maps is currently out of use. We'll try to get it back as soon as possible.</em>
			<br /><br />
			<a href="http://hitchwiki.org/maps" target="_blank"><img src="http://hitchwiki.org/maps/badge.png" alt="Hitchwiki Maps" /></a>
		</div>
	</body>
</html><?php
	
	#include("maintenance_page.php");
	exit;
} // end of maintenance


/*
 * Map settings
 */

// Defaults
$d_zoom = '5';
$d_lat = '51';
$d_lon = '9';

// Show a country
if(isset($_GET["country"]) && !empty($_GET["country"]) && strlen($_GET["country"]) == 2) {

		start_sql(); // from lib/functions.php
		
    	$query = "SELECT `iso`,`lat`,`lon`,`zoom` FROM `t_countries` WHERE `iso` = '".mysql_real_escape_string(strtoupper($_GET["country"]))."'";

	    // Build an array
   		$res = mysql_query($query);
   		if(!$res OR mysql_num_rows($res)==0) {
   			$zoom = $d_zoom;
   			$lat = $d_lat;
   			$lon = $d_lon;
			$alert = true;
   		}
   		else {
			while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
   			    $zoom = $r["zoom"];
   			    $lat = $r["lat"];
   			    $lon = $r["lon"];
   			}
   		}
   		
}
// Show free spot
else { 
	// Zoom, lat, lon, layers
	$zoom = (isset($_GET["zoom"]) && ctype_digit($_GET["zoom"])) ? $_GET["zoom"] : $d_zoom;
	
	// Centered to Germany (51,9). Projection center would be '49','8.3'
	$lat = (isset($_GET["lat"]) && is_numeric($_GET["lat"])) ? $_GET["lat"] : $d_lat;
	$lon = (isset($_GET["lon"]) && is_numeric($_GET["lon"])) ? $_GET["lon"] : $d_lon;
}

$basehref = "../";

?><!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" dir="ltr" lang="<?php echo shortlang(); ?>">
	<head profile="http://gmpg.org/xfn/11">
		<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
		<title>Hitchwiki - <?php echo _("Maps"); ?></title>
        <!--<base href="../" />-->
        <meta name="robots" content="noindex, nofollow" />
        <link rel="stylesheet" type="text/css" href="../static/css/widget.css<?php if($settings["debug"]==true) echo '?cache='.date("jnYHis"); ?>" media="all" />
        
        <script src="../static/js/jquery.min.js" type="text/javascript"></script>
        <script src="http://openlayers.org/api/OpenLayers.js" type="text/javascript"></script>
        <script type="text/javascript">
		//<![CDATA[

			/*
			 * Default map settings
			 */
			var lat = <?php echo $lat; ?>;
			var lon = <?php echo $lon; ?>;
			var zoom = <?php echo $zoom; ?>;
			
			var language = '<?php echo $settings["language"]; ?>';
			var read_more_txt = '<?php echo _("Read more..."); ?>';
			
			<?php if($alert) echo 'alert("Hitchwiki - '._("Maps").': '._("Requested country could not be found!").'");' ?>
		//]]>
        </script>
		<script src="../static/js/widget.js<?php if($settings["debug"]==true) echo '?cache='.date("jnYHis"); ?>" type="text/javascript"></script>
		
		<meta name="description" content="<?php printf(_("This is just a preview map. Go to %s for the actual service."), $settings["base_url"]."/"); ?>" />
	</head>
	<body>
	    <small id="loading-bar"><?php echo _("Loading..."); ?></small>

		<div id="map">
			<br /><br />
			<?php echo _("Loading..."); ?>
		</div>

		<ul id="log" style="display:none;"></ul>

	</body>
</html>