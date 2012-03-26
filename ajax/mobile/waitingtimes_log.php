<?php
/*
 * Hitchwiki Mobile Maps: waitingtimes_log.php
 * Show a waiting time log for a place
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
						`waitingtime`,
						`datetime`			
					FROM `t_waitingtimes` 
					WHERE `fk_point` = '".mysql_real_escape_string($_GET["id"])."'");
					
if(!$res) {
	error_sign();
	die();
}

// If found timings, go:
if(mysql_affected_rows() >= 1):

	// Gather data first into an array, so we can tell if there 
	// were records by current user, and print out little different <thead>

	$waitingtime_min = false;
	$waitingtime_max = false;
	while($r = mysql_fetch_array($res, MYSQL_ASSOC)) {
	
		if($r["waitingtime"] < $waitingtime_min OR $waitingtime_min === false) $waitingtime_min = $r["waitingtime"];
		if($r["waitingtime"] > $waitingtime_max OR $waitingtime_max === false) $waitingtime_max = $r["waitingtime"]; 
	
		$waitingtimes[] = array(
			"datetime" 		=> strtotime($r["datetime"]),
			"waitingtime" 	=> nicetime($r["waitingtime"]),
			"username" 		=> username($r["fk_user"]),
			"user_id" 		=> $r["fk_user"],
			"id" 		=> $r["id"]
		);
		
	}
	
	?>
	<br />
	<?php
	if(count($waitingtimes) > 2) {
		printf('<p>'._("Waiting time varies from %s to %s.").'</p>', nicetime($waitingtime_min), nicetime($waitingtime_max));
	}
	?>
	<table cellpadding="0" cellspacing="0" class="infotable smaller" id="timing_list">
		<thead>
		    <tr>
		    	<th><?php echo _("Date"); ?></th>
		    	<th><?php echo _("Waiting time"); ?></th>
		    	<th><?php echo _("User"); ?></th>
		    </tr>
		</thead>
		<tbody>
	<?php
	
	// Print out the array
	foreach($waitingtimes as $waitingtime) {
	
		echo '<tr id="timing-'.$waitingtime["id"].'">';
		
		// Datetime
		echo '<td title="'.date(DATE_RFC822, $waitingtime["datetime"]).'">'.date("n/Y", $waitingtime["datetime"]).'</td>';
		
		// Waitingtime
		echo '<td>'.$waitingtime["waitingtime"].'</td>';
		
		// Username
		echo '<td>';
		
		if(!empty($waitingtime["user_id"])) {
		
			// You?
			if(!empty($user["id"]) && $user["id"] == $waitingtime["user_id"]) echo '<strong>'.$waitingtime["username"].'</strong>';
			else echo $waitingtime["username"];
		
		} else echo $waitingtime["username"];
		
		echo '</td>';
		
		echo '</tr>';
	}
	
	?>
		</tbody>
	</table>

<?php else: ?>
	<p><i><?php echo _("No waiting time for this place added yet."); ?></i></p>
<?php endif; ?>