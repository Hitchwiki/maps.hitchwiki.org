
<h4><?php echo _("Download markers as a file"); ?></h4>

<small><em>Note, this feature is still experimental. If you face any problems, please report us by clicking "contact us" link on the left-bottom of the page.</em></small>

<form>
<div id="fileloader" style="overflow:hidden;width:1px;height:1px;"></div>

<ul class="clean">
	<li><a href="#" id="download_world"><?php echo _("World"); ?></a> <small>(<?php echo total_places()." "._("markers"); ?>)</small></li>
<!--	<li><a href="#" id="download_visible"><?php echo _("Visible area on the map"); ?></a> <small>(# <?php echo _("markers"); ?>)</li>-->
	<li><label for="download_continent"><?php echo _("Continent"); ?>:</label> <select id="download_continent" name="download_continent">
		<option value=""><?php echo _("Select"); ?></option>
		<?php list_continents("option",true); ?>
	</select></li>
	<li><label for="download_country"><?php echo _("Country"); ?>:</label> <select id="download_country" name="download_country">
		<option value=""><?php echo _("Select"); ?></option>
		<?php list_countries("option", "name"); ?>
	</select></li>
</ul>

<b><?php echo _("Format"); ?>:</b><br />
<input type="radio" name="format" value="gpx" id="gpx" disabled="disabled" /> <label for="gpx">GPX <i>(coming)</i></label><br />
<input type="radio" name="format" value="kml" id="kml" checked="checked" /> <label for="kml">KML</label><br />
<!--<input type="radio" name="format" value="kmz" id="kmz" /> <label for="kmz">KMZ (<?php echo _("Zipped"); ?> KML)</label><br />-->

<script type="text/javascript">
	$(function() {
		// Download:

		// Continent
		$("#download_continent").change( function() { 
			var download_value = $(this).val();
			var format_value = $('input[name="format"]:checked').val();
			fileloader('continent='+download_value, 'continent-'+download_value, format_value);
		});

		// Country
		$("#download_country").change( function() { 
			var download_value = $(this).val();
			var format_value = $('input[name="format"]:checked').val();
			fileloader('country='+download_value, 'country-'+download_value, format_value);
		});

		// World
		$("#download_world").click( function(e) { 
			e.preventDefault();
			var format_value = $('input[name="format"]:checked').val();
			fileloader('all', 'world', format_value);
		});

		// Visible area on the map
		$("#download_visible").click( function(e) { 
			e.preventDefault();
			var format_value = $('input[name="format"]:checked').val();
			alert("Not in use yet.");//TODO
		});

		// Autostart downloading with dynamic iframe
		function fileloader(url,name,format) {
			maps_debug("Downloading a "+format+" file: "+name+"."+format);
			$("#fileloader").html('<iframe src="api/?format='+format+'&amp;download='+name+'&amp;'+url+'" width="0" height="0" style="border:0; overflow: hidden; margin: 0;" scrolling="no" frameborder="0" allowtransparency="true"></iframe>');
		}

	});
</script>
</form>

<hr />

<p><small>
	<a href="http://wiki.openstreetmap.org/wiki/Converting_GPS_track_data_between_formats" class="icon help"><?php echo _("Read about converting data between formats"); ?></a>
	<br /><br />
	<a href="http://www.openstreetmap.org/export?lat=67.2&lon=-118.5&zoom=4&layers=M" class="icon icon-osm"><?php echo _("Use Open Street Map Export tool"); ?></a>
</small></p>
