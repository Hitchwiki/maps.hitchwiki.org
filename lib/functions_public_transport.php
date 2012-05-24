<?php
/* Hitchwiki - maps
 * Public transportation functions
 * - pt_types()
 * - pt_type()
 * - pt_list()
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
							 	<a href="<?= $settings["base_url"]; ?>/admin/?page=public_transport&amp;remove=<?php echo $row["id"]; ?>" class="remove_page ui-icon ui-icon-trash align_right" title="<?php echo _("Remove page permanently"); ?>"></a>
							 	<a href="<?= $settings["base_url"]; ?>/admin/?page=public_transport&amp;edit=<?php echo $row["id"]; ?>" class="ui-icon ui-icon-pencil align_right" title="<?php echo _("Edit page"); ?>"></a>
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
		<p><?php echo _("No public transport found for this country."); ?> <a href="<?= $settings["base_url"]; ?>/add_public_transport/" onclick="open_page('add_public_transport'); return false;"><?php echo _("Add some?"); ?></a></p>
		<?php
	}
}

?>