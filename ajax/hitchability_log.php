<?php
/*
 * Hitchwiki Maps: hitchability.php
 * Show a ratings log for a place
 */

/*
 * Load config to set language and stuff
 */
require_once "../config.php";

start_sql();

/*
 * Returns an info-array about logged in user (or false if not logged in) 
 */
$user = current_user();


/* 
 * Check ID
 */
if(!isset($_GET["id"]) OR !is_numeric($_GET["id"])) {
	error_sign();
	exit;
}


/* 
 * List out
 */

// Build an array
$res = mysql_query("SELECT 
						`id`,
						`fk_user`,
						`fk_point`,
						`rating`,
						`datetime`			
					FROM `t_ratings` 
					WHERE `fk_point` = '".mysql_real_escape_string($_GET["id"])."'");
					
if(!$res) {
	error_sign();
	die();
}

// If found timings, go:
if(mysql_affected_rows() >= 1):

	// Gather data first into an array, so we can tell if there 
	// were records by current user, and print out little different <thead>
	$current_user_rows = false;
	while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
	
	
		if(!empty($r["datetime"])) $datetime = strtotime($r["datetime"]);
		else $datetime = "";
		
		$ratings[] = array(
			"datetime" 		=> $datetime,
			"rating" 		=> hitchability2textual($r["rating"]),
			"username" 		=> username($r["fk_user"]),
			"user_id" 		=> $r["fk_user"],
			"id" 		=> $r["id"]
		);
		
		if($user["id"] == $r["fk_user"]) $current_user_rows = true;
	}
	
	?>
	
	
	<?php 
	// If more than 1 rating, show more complicated statistics
	
	$place = get_place($_GET["id"],true);
	
	if(isset($_GET["stats"])): ?>
	    <br /><small><?php echo _("Vote distribution"); ?>:</small><br />
	    <!--<img src="<?php echo rating_chart($place["rating_stats"], 220); ?>" alt="<?php echo _("Vote distribution"); ?>" />-->
	    <?php echo rating_chart_html($place["rating_stats"]); ?>
	<?php endif; ?>

	<br />
	<small><?php echo _("Hitchability").": ".round($place["rating_stats"]["exact_rating"], 1); ?>/5</small>
	<table cellpadding="0" cellspacing="0" class="infotable smaller" id="rating_list">
		<thead>
		    <tr>
		    	<th><span class="ui-icon ui-icon-calendar"><?php echo _("Date"); ?></span></th>
		    	<th><span class="ui-icon ui-icon-star"><?php echo _("Hitchability"); ?></span></th>
		    	<th><span class="ui-icon ui-icon-person"><?php echo _("User"); ?></span></th>
		    	<?php if($current_user_rows===true) echo '<th> </th>'; ?>
		    </tr>
		</thead>
		<tbody>
	<?php
	
	// Print out the array
	foreach($ratings as $rating) {
	
		echo '<tr id="rating-'.$rating["id"].'">';
		
		if(!empty($rating["datetime"])) echo '<td title="'.date(DATE_RFC822, $rating["datetime"]).'">'.date("n/Y", $rating["datetime"]).'</td>';
		else echo '<td> </td>';
		
		echo '<td>'.$rating["rating"].'</td>';
		
		if(!empty($user["id"]) && $user["id"] == $rating["user_id"]) echo '<td><a href="./?page=profile" onclick="open_page(\'profile\'); return false;">'.$rating["username"].'</a></td>';
		else echo '<td>'.$rating["username"].'</td>';
		
		// Print extra cell if in this list there are some of this users waitingtimes. 
		// Print delete-icon into users own rows
		if($current_user_rows===true) {
			if($user["id"] == $rating["user_id"] OR $user["admin"] === true) echo '<td><a href="#" class="remove_rating ui-icon ui-icon-trash align_right" title="'._("Remove record").'">'.$rating["id"].'</a></td>';
			else echo '<td> </td>';
		}
		
		echo '</tr>';
	}
	
	?>
		</tbody>
	</table>
	
	<script type="text/javascript">
		$(function() {
		
		    // Remove rating
		    $(".remove_rating").click(function(e) {
		    	e.preventDefault();
		    	
				var remove_id = $(this).text();
	
	    		maps_debug("Asked to remove rating "+remove_id);
				stats("rating/remove/");
				
				var confirm_remove = confirm("<?php echo _("Are you sure you want to remove this record?"); ?>")
				
				if(confirm_remove) {
					// Call API
					$.getJSON('api/?remove_rating&rating_id='+remove_id, function(data) {
					
						if(data.success == true) {
					
	    					maps_debug("Rating "+remove_id+" removed.");
						
							// Fade rating away
	    					//$("#timing_list #timing-"+remove_id).fadeOut("slow");
	    					showPlacePanel(<?php echo htmlspecialchars($_GET["id"]); ?>);
	    			
	    					
	    				// Produces an error popup if current logged in user doesn't have permissions or some other error happened
						} else {
							info_dialog("<?php echo _("Could not remove a record due to an error. Please try again!"); ?>", "<?php echo _("Error"); ?>", true);
	    					maps_debug("Could not remove rating. Error: "+data.error_description);
						}
					
					});
				}
	
		    });
	
		});
	</script>

<?php else: ?>
	<p><i><?php echo _("No ratings for this place added yet."); ?></i></p>
<?php endif; ?>