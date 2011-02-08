<?php


	$id = "5771";//"2722";

	$lines = gather_log($id);
	$place = get_place($id, true);
	

?><h2><?php echo _("Edit history for a place"); ?></h2>

<h3><?php 

	// Flag
	if(!empty($place["location"]["country"]["iso"])) echo '<img class="flag" alt="'.$place["location"]["country"]["iso"].'" src="static/gfx/flags/'.strtolower($place["location"]["country"]["iso"]).'.png" /> ';
	
	// Town/City
	if(!empty($place["location"]["locality"])) echo $place["location"]["locality"].", ";
	
	// Country
	if(!empty($place["location"]["country"]["name"])) echo $place["location"]["country"]["name"];
	
?></h3>

<div style="width: 650px;">
<ul class="history">
<?php
	
	if(is_array($lines) && !empty($lines)) {
	foreach($lines as $line) {
	
		// empty datetime?
		// Try to get rid of these already at the query...
		if(!empty($line["datetime"])){
		
		// Icon
		if($line["log_type"] == "comment") $icon = 'comment';
		elseif($line["log_type"] == "place") $icon = 'map';
		elseif($line["log_type"] == "waitingtime") $icon = 'time';
		elseif($line["log_type"] == "rating") $icon = 'chart_bar2';
		elseif($line["log_type"] == "description") $icon = 'pencil';
		else $icon = 'tag';
		
		// START
		echo '<li id="log-'.$line["log_type"].'-'.$line["id"].'" class="log_'.$line["id"].' icon '.$icon.'">';
	
		// Who
		if(!empty($line["fk_user"])) $who = '<b>'.username($line["fk_user"]).'</b>';
		else $who = _("Anonymous");

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
			echo sprintf(_("%s added or edited description of the place"), $who);
			echo '<br /><small><em class="bubble">'.Markdown($line["log_entry"]).'</em></small>';
		}


		// When
		echo '<br /><small title="'.date(DATE_RFC822,strtotime($line["datetime"])).'"><a href="./?page=place_history&amp;place='.$place["id"].'#log-'.$line["log_type"].'-'.$line["id"].'">'.date("j.n.Y H:i",strtotime($line["datetime"])).'</a>';
		
		// IP for Admins
		if($user["admin"] === true && !empty($line["ip"])) echo ' &mdash; <a href="http://ip-lookup.net/?'.$line["ip"].'" title="IP">'.$line["ip"].'</a>';
		
		echo '</small>';

		// END
		echo '</li>';
		
		// empty datetime?
		}	
	}
	// Is $lines array?
	} else echo '<li>'.error_sign(_("This place doesn't have log events."),false).'</li>';
?>
</ul>

</div>