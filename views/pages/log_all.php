<?php

	$lines = gather_log();

?><h2><?php echo _("Log"); ?></h2>

<div style="width: 650px;">
<p><?php printf(_("Actions on a website during the last %d days."), 7); ?></p>

<ul class="history">
<?php

	if(is_array($lines) && !empty($lines)) {
	foreach($lines as $line) {
	
		#echo '<pre>'.print_r($line,true).'</pre>';
		
		// empty datetime?
		// Try to get rid of these already at the query...
		if(!empty($line["datetime"])){
		
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
		elseif($line["log_type"] == "public_transport") { 
			echo sprintf(_('%1$s added a link to public transportation info in %2$s'), $who, '<b>'.ISO_to_country($line["log_entry"]).'</b>');
		}
		elseif($line["log_type"] == "user") { 
			echo sprintf(_("%s started using Maps"), $who);
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
	} else echo '<li>'.error_sign(_("Could not load log."),false).'</li>';
?>
</ul>

</div>