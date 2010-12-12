<h2><?php echo _("Members"); ?></h2>

<?php if($user["logged_in"]===true): ?>

<?php

	// Built up a query
	$query = "SELECT `id`,`admin`,`name`,`registered`,`last_seen`,`location`,`country` FROM `t_users` ORDER BY `name`,`registered` ASC";
	
	// Gather data
	start_sql();
	$result = mysql_query($query);
	if (!$result) {
	   die("Error: SQL query failed.");
	}
	
	$usercount = mysql_num_rows($result);
	
	// If some results, print out
	if($usercount >= 1) {
?>

	<p><?php printf(_("We have %s registered hitchhikers using Maps!"), $usercount); ?></p>
	
	<table class="infotable" id="users_list" cellspacing="0" cellpadding="0">
	    <thead>
	    	<tr>
	    		<th><?php echo _("User"); ?></th>
	    		<th><?php echo _("Using Maps since"); ?></th>
	    		<th><?php echo _("Last seen"); ?></th>
	    		<th><?php echo _("Location"); ?></th>
	    		<th><?php echo _("Country"); ?></th>
	    		
	    		<?php if($user["admin"]===true): ?>
	    			<th title="<?php echo _("Visible only for admins"); ?>"><?php echo _("Admins"); ?></th> 
	    		<?php endif; ?>
	    	</tr>
	    </thead>
	    <tbody>
	    	<?php
	    	// Print out page rows
			while ($row = mysql_fetch_array($result)) {
	    		echo '<tr valign="top">';
	    		
	    		// Name
	    		if($row["id"] == $user["id"]) echo '<td><b><a href="./?page=profile" onclick="open_page(\'profile\'); return false;">'.htmlspecialchars($row["name"]).'</a></b> <small>&mdash; '._("That's you!").'</small></td>';
	    		else echo '<td>'.htmlspecialchars($row["name"]).'</td>';
	    		
	    		// Registered
	    		echo '<td style="text-align: right;">'.date("j.n.Y", strtotime($row["registered"])).'</td>';
	    		
	    		// Last time seen
	    		if(!empty($row["last_seen"])) echo '<td style="text-align: right;">'.date("j.n.Y", strtotime($row["last_seen"])).'</td>';
	    		else echo '<td> </td>';
	    		
	    		// Location
	    		if(!empty($row["location"])) {
	    			echo '<td><a href="#" class="search_this">'.htmlspecialchars($row["location"]).'</td>';
	    		}
	    		else echo '<td> </td>';
	    		
	    		
	    		// Country
	    		if(!empty($row["country"])) {
	    			echo '<td><a href="#" class="search_this">'.ISO_to_country($row["country"]).'</a> <img class="flag" alt="" src="static/gfx/flags/'.strtolower($row["country"]).'.png" /></td>';
	    		}
	    		else echo '<td> </td>';
	    		
	    		
	    		// Tools for admins
	    		if($user["admin"]===true) {
	    			
	    			// Is admin?
	    			if($row["admin"] == '1') echo '<td class="icon tux">';
	    			else echo '<td>';
					?>
						<a href="admin/?page=users&amp;remove=<?php echo $row["id"]; ?>" class="remove_user ui-icon ui-icon-trash align_right" title="<?php echo _("Remove user permanently"); ?>"></a>
						<a href="admin/?page=users&amp;edit=<?php echo $row["id"]; ?>" class="ui-icon ui-icon-pencil align_right" title="<?php echo _("Edit user"); ?>"></a>
					</td>
					<?php
	    		} // only for admins
	    		
	    		echo '</tr>';
	    	}
	    	?>
	    </tbody>
	</table>
	
	<script type="text/javascript">
	$(function() {
	    
	    $("#users_list .search_this").click(function(e){
	    	e.preventDefault();
	    	close_page();
	    	search($(this).text());
	    });
	    
		<?php if($user["admin"]===true): ?>
	    // Confirm delete
	    $("#users_list .remove_user").click(function(e){
	    	e.preventDefault();
	    	
	    	if(confirm('<?php echo _("Are you sure?"); ?>')) {
	    		$(location).attr('href', $(this).attr("href"));
	    	}
	    });
		<?php endif; ?>
	
	});
	</script>

<?php
	} // if found users?
	

?>
<?php else: ?>

	<div class="ui-state-error ui-corner-all" style="padding: 0 .7em; margin: 20px 0;"> 
	    <p><span class="ui-icon ui-icon-alert" style="float: left; margin-right: .3em;"></span> 
	    <?php echo _("You must be logged in to view users."); ?></p>
	</div>
	
<?php endif; ?>