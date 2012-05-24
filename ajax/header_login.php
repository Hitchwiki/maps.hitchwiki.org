<?php
/* Hitchwiki Maps - Header - Login area
 * Called with AJAX from the frontpage
 */
if(!$loginRefreshArea) {
	require_once("../config.php");
	$user = current_user();
}
?>
					<ul id="loginMenu" class="<?php
							if($user["logged_in"]===true) echo 'logged_in';
							else echo 'logged_out';
						?>">
						
					<?php // User is logged in:
					if($user["logged_in"]===true): ?>
						<li><a href="http://hitchwiki.org/en/index.php?title=Special:UserLogout&returnto=Maps.hitchwiki.org" id="logout"><?php echo _("Logout"); ?></a></li>
						<li><a href="<?= $settings["base_url"]; ?>/settings/" onclick="open_page('settings'); return false;"><?php echo _("Settings"); ?></a></li>
						<li class="hello"><span class="icon <?php
						
						/*
						 * Icon
						 */
						if($settings["language"]=='pirate') echo 'skull'; // Yarr!
						elseif($user["admin"]===true) echo 'tux'; // ;-)
						else echo 'user_orange'; // default
						
						echo '"'; //end class
						
						// Gravatar
						//if($user["allow_gravatar"]=="1" && !empty($user["email"])) echo ' style="background-image: url(http://www.gravatar.com/avatar/'.md5($user["email"]).'/?s=16);"';
						
						echo '>'; //end tag
						
						
						/*
						 * Pick one random hello
						 */
						$hello = array(
							"Hi!" => "GB",
							"Hello!" => "GB",
							"Tere!" => "EE",
							"Hei!" => "FI",
							"Moi!" => "FI",
							"¡Hola!" => "ES",
							"Shalom!" => "IL",
							"Namaste!" => "NP",
							"Namaste!" => "IN",
							"Mambo!" => "CG",
							"Bok!" => "HR",
							"Hallo!" => "NL",
							"Hallo!" => "DE",
							"Moin!" => "DE",
							"Servus!" => "DE",
							"Grüß Gott!" => "AU",
							"Hej!" => "DK",
							"Hej!" => "SE",
							"Hejsan!" => "SE",
							"Ciào!" => "IT",
							"Labas!" => "LT",
							"Sveikas!" => "LT",
							"Sveiki!" => "LV",
							"Moïen!" => "LU",
							"Salamaleikum," => "SN",
							"Čau!" => "SK",
							"Hoezit!" => "ZA",
							"Jambo!" => "KE",
							"Selam!" => "TR",
							"Sawatdee!" => "TH"
						);
						$hello_greeting = array_rand($hello,1);
						
						?><span title="<?php printf(_("Hello from %s"), ISO_to_country($hello[$hello_greeting])); ?>"><?php echo $hello_greeting; ?></span>
						<a href="<?= $settings["base_url"]; ?>/profile/" id="profile" onclick="open_page('profile'); return false;" title="<?php echo _("Profile"); ?>"><?php echo $user["name"]; ?></a></span></span></li>
					<?php else: ?>
						<li class="login"><a href="http://hitchwiki.org/en/index.php?title=Special:UserLogin&amp;returnto=Maps.hitchwiki.org" id="loginOpener" class="icon lock align_right"><?php echo _("Login"); ?></a></li>
						<li><a href="<?= $settings["base_url"]; ?>/why_register/" id="why_register" onclick="open_page('why_register'); return false;"><?php echo _("Why register?"); ?></a></li>
						<li><a href="http://hitchwiki.org/en/index.php?title=Special:UserLogin&amp;type=signup&amp;returnto=Maps.hitchwiki.org" id="register"><?php echo _("Register!"); ?></a></li>
					<?php endif; ?>
					</ul>