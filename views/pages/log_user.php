<?php
echo info_sign("This feature is under development and visible only for admins.",false);

// Show only when logged in
if($user["logged_in"]===true): 

if(isset($_GET["user_id"]) && !empty($_GET["user_id"])) $profile = user_info($_GET["user_id"]);
else $profile = $user;


if($user["id"] == $profile["id"]): ?>
	<h2><?php printf(_("Hey %s, welcome to your stuff!"), '<a href="./?page=profile" onclick="open_page(\'profile\'); return false;" title="'._("Profile").'">'.$profile["name"].'</a>'); ?></h2>
<?php else: ?>
	<h2><?php printf(_("%s's activity log"), '<a href="./?page=profile&amp;user_id='.$profile["id"].'" onclick="open_page(\'profile\', \'user_id='.$profile["id"].'\'); return false;" title="'._("Profile").'">'.$profile["name"].'</a>'); ?></h2>
<?php endif; ?>

<div style="width: 650px;">
<ul class="history">
<?php
	
	$lines = gather_log($profile["id"], "user");
	
	if(is_array($lines) && !empty($lines)) {
	foreach($lines as $line) {
	
		// empty datetime?
		// Try to get rid of these already at the query...
		//if(!empty($line["datetime"]) OR $line["log_type"] == "place"){
		
		// Icon
		if($line["log_type"] == "comment") $icon = 'comment';
		elseif($line["log_type"] == "place") $icon = 'map';
		elseif($line["log_type"] == "waitingtime") $icon = 'time';
		elseif($line["log_type"] == "rating") $icon = 'chart_bar2';
		elseif($line["log_type"] == "description") $icon = 'pencil';
		elseif($line["log_type"] == "public_transport") $icon = 'underground';
		elseif($line["log_type"] == "user") $icon = 'user';
		else $icon = 'tag';
		
		// START
		echo '<li id="log-'.$line["log_type"].'-'.$line["id"].'" class="log_'.$line["id"].' icon '.$icon.'">';
	
		// Place
		$place = (!empty($line["fk_point"])) ? place_name($line["fk_point"], true): false;
		
		// Who
		$who = '<strong>'.$profile["name"].'</strong>';//(!empty($line["fk_user"])) ? '<strong>'.username($line["fk_user"], true).'</strong>': _("Anonymous");

		// What
		if($line["log_type"] == "place") { 
			echo sprintf(_('%s added a new place'), $who);
		}
		elseif($line["log_type"] == "comment") { 
			echo sprintf(_("%s commented place"), $who);
			echo '<br /><small><em class="bubble">'.Markdown($line["log_entry"]).'</em></small>';
		}
		elseif($line["log_type"] == "waitingtime") { 
			echo sprintf(_('%1$s waited for a ride in here for %2$s'), $who, nicetime($line["log_entry"]));
		}
		elseif($line["log_type"] == "rating") { 
			echo sprintf(_('%1$s rated "%2$s" for this place'), $who, hitchability2textual($line["log_entry"]));
		}
		elseif($line["log_type"] == "description") { 
			echo sprintf("%s added or edited a description of the place", $who);
			#echo sprintf(_("%s added or edited a description of the place"), $who);
			if(!empty($line["log_meta"])) echo '<br /><small title="'._("Language").'">'._("Language").': '._($settings["languages_in_english"][$line["log_meta"]]).'</small>';
			echo '<br /><small><em class="bubble">'.Markdown(utf8_decode($line["log_entry"])).'</em></small>';
		}
		elseif($line["log_type"] == "public_transport") { 
			echo sprintf(_('%1$s added a link to the public transportation catalog for %2$s'), $who, '<b>'.ISO_to_country($line["log_entry"]).'</b>');
		}
		elseif($line["log_type"] == "user") { 
			echo sprintf(_("%s started using Maps"), $who);
		}


		// Start meta
		echo '<br /><small>';
		
			// Place
			if($place !== false && !empty($place)) echo $place.'<br />';

			// When
			if(!empty($line["datetime"])) echo '<a href="./?page=place_history&amp;place='.$place["id"].'#log-'.$line["log_type"].'-'.$line["id"].'" title="'.date(DATE_RFC822,strtotime($line["datetime"])).'">'.date("j.n.Y H:i",strtotime($line["datetime"])).'</a>';
			else echo _("Before 27. November 2010");
		
			// IP for Admins
			if($user["admin"] === true && !empty($line["ip"])) echo ' &mdash; <a href="http://ip-lookup.net/?'.$line["ip"].'" title="IP">'.$line["ip"].'</a>';
		
		// End meta
		echo '</small>';

		// END
		echo '</li>';
		
		// empty datetime?
		//}
	}
	// Is $lines array?
	} else echo '<li><br /><br />'.info_sign(_("User hasn't been poking around the site yet."),false).'<br /><br /></li>';
?>
</ul>

</div>

<?php 
// Not logged in?
else: 
	error_sign(_("You must be logged in."), false);
endif;

?>