<?php
/* Hitchwiki Maps - Header - Navi area
 * Called with AJAX from the frontpage
 */
if (!isset($naviRefreshArea)) {
	require_once("../config.php");
	$user = current_user();
}
?>
<?php /*
				<?php if($user["logged_in"]===true): ?>
					<li><a href="<?= $settings["base_url"]; ?>/users/" id="users" class="icon user" onclick="open_page('users'); return false;"><?php echo _("Members"); ?></a></li>
				<?php else: ?>
					<li><a href="<?= $settings["base_url"]; ?>/about/" id="about" class="icon help" onclick="open_page('about'); return false;"><?php echo _("About"); ?></a></li>
				<?php endif; ?>

		    	<?php // Visible only for admins
			    	if($user["admin"]===true): ?>
					<!--<li><a href="#" id="streetview" class="icon eye cardlink"><?php echo _("Street view"); ?></a></li>-->
					<li><a href="./?page=trips" id="trips" class="icon flag_green" onclick="open_page('trips'); return false;"><?php echo _("My trips"); ?></a></li>
				<?php endif; ?>

					<li><a href="<?= $settings["base_url"]; ?>/log_all/" id="log_all" class="icon page_white_text" onclick="open_page('log_all'); return false;"><?php echo _("Log"); ?></a></li>
*/ ?>

						    	<li id="menu-item-121" class="menu-item"><a href="http://hitchwiki.org/en/">Wiki</a></li>
						    	<li id="menu-item-122" class="menu-item current-menu-item current_page_item"><a href="http://hitchwiki.org/maps/">Maps</a></li>
						    	<li id="menu-item-116" class="menu-item"><a href="http://hitchwiki.org/activity/">Activity</a></li>
						    	<li id="menu-item-117" class="menu-item"><a href="http://hitchwiki.org/blogs/">Blogs</a></li>
						    	<li id="menu-item-118" class="menu-item"><a href="http://hitchwiki.org/forums/">Forums</a></li>
						    	<li id="menu-item-119" class="menu-item"><a href="http://hitchwiki.org/groups/">Groups</a></li>
						    	<li id="menu-item-120" class="menu-item"><a href="http://hitchwiki.org/members/">Members</a></li>
						    	<li id="menu-item-147" class="menu-item"><a href="http://hitchwiki.org/chat/">Chat</a></li>
