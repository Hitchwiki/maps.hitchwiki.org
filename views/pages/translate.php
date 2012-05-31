
<h3><?php printf(_("Hitchwiki Maps is currently available in %s languages"), count($settings["valid_languages"])); ?>:</h3>

<ul class="clean" style="width: 300px;">
<?php 
// Print out a list of current languages
foreach($settings["valid_languages"] as $code => $lang) {

	echo '<li><a href="'.$settings["base_url"].'/?page=translate&amp;lang='.$code.'" title="'._("Choose language").'"><img class="flag" alt="" src="'.$settings["base_url"].'/static/gfx/flags/'.strtolower(substr($code, -2)).'.png" /> '.$lang.'</a> - '._($settings["languages_in_english"][$code]).'</li>';

}

?>
</ul>

<h3><?php echo _("Help us with translating!"); ?></h3>

<p><?php echo _("If you would like to add content in your own language, or translate all visible interface texts, contact us so we can put up a new language."); ?></p>

<p><b><a href="#" class="icon email" onclick="javascript:open_card('contact','<?php echo _("Contact us!"); ?>'); return false;"><?php echo _("Contact us!"); ?></a></b></p>

<p><?php printf(_("You can see the current status of translations from %s"), '<a href="http://hitchwiki.org/translate/projects/maps/" target="_blank">hitchwiki.org/translate/</a>'); ?></p>