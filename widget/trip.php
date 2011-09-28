<?php
/*
 * Initialize Maps
 */
if(@is_file('../config.php')) require_once "../config.php";
else { $settings["maintenance_page"] = true; $settings["non_maintenance_ip"] = array(); }

$settings["debug"] = true;

/*
 * Put up a maintenance -sign
 * Set it up from config.php or test it from ./?maintenance
 */
if(isset($_GET["maintenance"])) $settings["maintenance_page"] = true;
if($settings["maintenance_page"]===true && !in_array($_SERVER['REMOTE_ADDR'], $settings["non_maintenance_ip"])) {

	include("maintenance_widget.php");
	exit;
} // end of maintenance


// Validate user and permitted to publish trips?
if(!isset($_GET["user_id"]) OR empty($_GET["user_id"])) $user_info = false;
else $user_info = user_info($_GET["user_id"]);



// User validation failed
if($user_info == false OR $user_info["private_trips"] === true) {

	//if($user_info["private_location"] === true) $maintenance_text = "";
	if($user_info["private_trips"] === true) $maintenance_text = "User's trips are not public.";
	else $maintenance_text = "Oops! Something went wrong. Try again later!";

	include("maintenance_widget.php");
	exit;
}

// Get user's current location
$current_location = user_current_location($user_info["id"]);


/*
 * Map settings
 */

// Defaults (in Germany)
$zoom = '6';
$lat = '51';
$lon = '9';


// Location to the root: 
$basehref = "../";


// User's latest location
if($user_info["private_location"] != 1 && $current_location != false && !isset($current_location["error"])) {
	//$user_info["location"] = user_location($user_info["id"]);
	$zoom = '8';
	$lat = $current_location["lat"];
	$lon = $current_location["lon"];
}


// Show free spot -Zoom, lat, lon
if(isset($_GET["zoom"]) && !empty($_GET["zoom"]) && ctype_digit($_GET["zoom"])) $zoom = $_GET["zoom"];
if(isset($_GET["lat"]) && !empty($_GET["lat"]) && is_numeric($_GET["lat"])) $lat = $_GET["lat"];
if(isset($_GET["lon"]) && !empty($_GET["lon"]) && is_numeric($_GET["lon"])) $lon = $_GET["lon"];


// Selecting map layer
if($_GET["layer"] == "gmap"
   OR $_GET["layer"] == "ghyb"
   OR $_GET["layer"] == "gphy"
   OR $_GET["layer"] == "gsat"
   OR $_GET["layer"] == "osm" ) $map_layer = $_GET["layer"];
else $map_layer = "osm";


// Will we print footer?
if($current_location != false) $footer = true;

?><!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" dir="ltr" lang="<?php echo shortlang(); ?>">
	<head profile="http://gmpg.org/xfn/11">
	<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
	<title>Hitchwiki - <?php echo _("Maps")." - "._("Trips"); ?></title>
        <meta name="robots" content="noindex, nofollow" />
        <link rel="stylesheet" type="text/css" href="../static/css/widget.css?c=<?php 
			if($settings["debug"]==true) echo date("jnYHis"); 
			else echo $settings["cache_buster"];
		?>" media="all" />
        <link rel="stylesheet" type="text/css" href="../static/css/widget-trip.css?c=<?php 
			if($settings["debug"]==true) echo date("jnYHis"); 
			else echo $settings["cache_buster"];
		?>" media="all" />
        
        <script src="../static/js/jquery.min.js?c=<?php echo $settings["cache_buster"]; ?>" type="text/javascript"></script>
        <script src="http://openlayers.org/api/OpenLayers.js" type="text/javascript"></script>
	<?php
	// Load Google Maps API if needed
	if($map_layer == "gmap"
		OR $map_layer == "ghyb"
		OR $map_layer == "gphy"
		OR $map_layer == "gsat"): ?><script src="http://maps.google.com/maps?file=api&l=<?php echo shortlang(); ?>&v=2&key=<?php echo $settings["google_maps_api_key"]; ?>"></script><?php endif; ?>
        <script type="text/javascript">
		//<![CDATA[

			/*
			 * Map settings
			 */
			var lat = <?php echo $lat; ?>;
			var lon = <?php echo $lon; ?>;
			var zoom = <?php echo $zoom; ?>;
			var user_id = <?php echo $user_info["id"]; ?>;
			var map_layer = '<?php echo $map_layer; ?>';
			var language = '<?php echo $settings["language"]; ?>';
			var basehref = '<?php echo $basehref; ?>';
			var read_more_txt = '<?php echo _("Read more..."); ?>';
			<?php if($user_info["private_location"] > 1 && $current_location != false): ?>
			var show_current_location = true;
			var current_location_lat = <?php echo $current_location["lat"]; ?>;
			var current_location_lon = <?php echo $current_location["lon"]; ?>;
			var current_location_zoom = 8;
			<?php else: ?>
			var show_current_location = false;
			<?php endif; ?>
			
		//]]>
	</script>
	<script src="../static/js/widget-trip.js?c=<?php 
			if($settings["debug"]==true) echo date("jnYHis"); 
			else echo $settings["cache_buster"];
		?>" type="text/javascript"></script>
		
	<meta name="description" content="<?php printf(_("This is just a preview map. Go to %s for the actual service."), $settings["base_url"]."/"); ?>" />
	</head>
	<body<?php if($footer) echo ' class="with_footer"'; ?>>
	    <small id="loading-bar"><?php echo _("Loading..."); ?></small>

		<div id="map">
			<br /><br />
			<?php echo _("Loading..."); ?>
		</div>
		
		<?php if($footer): ?>
		<div id="footer">
		<?php
			// Current location	
			if($current_location != false) echo '<div class="current_location">'.user_current_location_link($user_info["id"]).'</div>';
		?>
		</div>
		<?php endif; ?>


		<ul id="log" style="display:none;"></ul>
	</body>
</html>