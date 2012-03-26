<?php
/*
 * Hitchwiki Mobile Maps: hitchability_log.php
 * Show a ratings log for a place
 */

/*
 * Load config to set language and stuff
 */
require_once "../../config.php";

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

	while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
	
	
	    if(!empty($r["datetime"])) $datetime = strtotime($r["datetime"]);
	    else $datetime = "";
	    
	    $ratings[] = array(
	    	"datetime" 		=> $datetime,
	    	"rating" 		=> hitchability2textual($r["rating"]),
	    	"rating_num" 	=> hitchability2numeric($r["rating"]),
	    	"username" 		=> username($r["fk_user"]),
	    	"user_id" 		=> $r["fk_user"],
	    	"id" 		=> $r["id"]
	    );
	    
	}
	
	?>
	
	
	<?php 
	// If more than 1 rating, show more complicated statistics
	
	$place = get_place($_GET["id"],true);
	
	if(isset($_GET["stats"])): ?>
	    <br /><small><?php echo _("Vote distribution"); ?>:</small><br />
	    <?php echo rating_chart_html($place["rating_stats"]); ?>
	<?php endif; ?>

	<br />
	<small><?php echo _("Hitchability").": ".hitchability2numeric($place["rating_stats"]["exact_rating"]); ?></small>
	<table cellpadding="0" cellspacing="0" class="infotable smaller" id="rating_list">
		<thead>
		    <tr>
		    	<th><<?php echo _("Date"); ?></th>
		    	<th><?php echo _("Hitchability"); ?></th>
		    	<th><?php echo _("User"); ?></th>
		    </tr>
		</thead>
		<tbody>
	<?php
	
	// Print out the array
	foreach($ratings as $rating) {
	
		echo '<tr id="rating-'.$rating["id"].'">';
		
		// Date
		if(!empty($rating["datetime"])) echo '<td title="'.date(DATE_RFC822, $rating["datetime"]).'">'.date("n/Y", $rating["datetime"]).'</td>';
		else echo '<td> </td>';
		
		// Rating
		echo '<td title="'.$rating["rating_num"].'">'.$rating["rating"].'</td>';
		
		// Username
		echo '<td>';

		if(!empty($rating["user_id"])) {
			
			// You?
			if(!empty($user["id"]) && $user["id"] == $rating["user_id"]) echo '<strong>'.$rating["username"].'</strong>';
			else echo $rating["username"];
		
		} 
		// Not registered user...
		else echo $rating["username"];
		
		echo '</td>';
		
		echo '</tr>';
	}
	
	?>
		</tbody>
	</table>
	
<?php else: ?>
	<p><i><?php echo _("No ratings for this place added yet."); ?></i></p>
<?php endif; ?>