<?php
/*
 * Hitchwiki Maps: profile.php
 */
 

if(isset($_GET["user_id"]) && !empty($_GET["user_id"])) $profile = user_info($_GET["user_id"]);
else $profile = $user;


if(!empty($profile)):

	// Get countryname, we'll need it
	if(!empty($profile["country"])) $countryname = ISO_to_country($profile["country"]);
	
?>
<header>
<?php if($user["id"] == $profile["id"]): ?>
	<h2><?php printf(_("Welcome home, %s"), $profile["name"]); ?></h2>
	<?php if(!empty($profile["country"])): ?><em><strong class="white"><?php printf(_("How's the weather in %s?"), $countryname); ?></strong></em><br/><?php endif; ?>
<?php else: ?>
	<h2><?php echo $profile["name"]; ?></h2>
<?php endif; ?>
</header>

<table class="infotable profile_card" cellspacing="0" cellpadding="0">
    <tbody>
    	
    	<?php if(!empty($profile["registered"])): ?>
    	<tr>
    		<td><b><?php echo _("Member since"); ?></b></td>
    		<td><?php echo date("j.n.Y", strtotime($profile["registered"])); ?></td>
    	</tr>
    	<?php endif; ?>
    	
    	
    	<?php if(!empty($profile["last_seen"])): ?>
    	<tr>
    		<td><b><?php echo _("Last seen"); ?></b></td>
    		<td><?php echo date("j.n.Y", strtotime($profile["last_seen"])); ?></td>
    	</tr>
    	<?php endif; ?>
    	
    	<?php if(!empty($profile["location"])): ?>
    	<tr>
    		<td><b><?php echo _("Location"); ?></b></td>
    		<td><a href="./?q=<?php echo urlencode($profile["location"]); ?>" id="search_for_this"><?php echo $profile["location"]; ?></a></td>
    	</tr>
    	<?php endif; ?>
    	
    	
    	<?php if(!empty($profile["country"])): ?>
    	<tr>
    		<td><b><?php echo _("Country"); ?></b></td>
    		<td><a href="./?q=<?php echo urlencode($countryname); ?>" id="search_for_this"><?php echo $countryname; ?></a> <img class="flag" alt="" src="static/gfx/flags/<?php echo strtolower($profile["country"]); ?>.png" /></td>
    	</tr>
    	<?php endif; ?>
    	
    	<?php if(!empty($profile["location"]) OR !empty($profile["country"])): ?>
		<script type="text/javascript">
		    $("a#search_for_this").click(function(e){
		    	e.preventDefault();
		    	search($(this).text(),true);
		    });
		</script>
    	<?php endif; ?>
    	
    	<?php if(!empty($profile["language"]) && isset($settings["languages_in_english"][$profile["language"]])): ?>
    	<tr>
    		<td><b><?php echo _("Language"); ?></b></td>
    		<td><?php echo _($settings["languages_in_english"][$profile["language"]]); ?></td>
    	</tr>
    	<?php endif; ?>
    	
    	<?php 
    	// Show if profile is of an admin
    	if($profile["admin"]===true): ?>
    	<tr>
    		<td colspan="2"><span class="icon tux"><?php echo _("Administrator"); ?></span></td>
    	</tr>
    	<?php endif; ?>
    	
    	<?php 
    	// Show this only for admins
    	if($user["admin"]===true): ?>
    	<tr>
    		<td colspan="2"><span class="icon page_white_text"><a href="#" onclick="open_page('log_user', 'user_id=<?php echo $profile["id"]; ?>'); return false;"><?php printf(_("%s's activity log"), $profile["name"]); ?></a></span></td>
    	</tr>
    	<tr>
    		<td colspan="2"><span class="icon key"><?php echo $profile["id"]; ?></span></td>
    	</tr>
    	<?php endif; ?>
    	
    	<?php 
    	/*
		 * Gravatar 
		 * http://en.gravatar.com/site/implement/
		 */
    	if(!empty($profile["email"]) && $profile["allow_gravatar"] == "1") {
		
			$str = file_get_contents( 'http://www.gravatar.com/'.md5($profile["email"]).'.php' );
			$gravatar = unserialize( $str );
			
			if ( is_array( $gravatar ) && isset( $gravatar['entry'] ) ) {
			
				?>
    			<tr>
    				<td colspan="2">
						<a href="<?php echo $gravatar['entry'][0]['profileUrl']; ?>"><img src="http://www.gravatar.com/avatar/<?php echo md5($profile["email"]); ?>/?s=200&amp;default=<?php echo urlencode($settings["base_url"]."/static/gfx/blank.gif"); ?>"  alt="<?php echo $gravatar['entry'][0]['displayName']; ?>" /></a>
						<br />
						<small><?php printf(_("Image from your %s"), '<a href="'.$gravatar['entry'][0]['profileUrl'].'" target="_blank" title="A Globally Recognized Avatar">Gravatar</a>'); ?></small>
    				</td>
    			</tr>
    			<?php 
    		} // gravatar found 
    	} // email ok and gravatar allowed 
    	?>
    	
    </tbody>
</table>

<?php if($profile["private_location"] > 1): ?>

    <?php if(!empty($profile["google_latitude"])): ?>
	<div class="location_map"><iframe src="http://www.google.com/latitude/apps/badge/api?user=<?php echo urlencode($profile["google_latitude"]); ?>&type=iframe&maptype=roadmap" width="400" height="400" frameborder="0"></iframe></div>
    <?php endif; ?>
    
    <?php // Visible only for admins
	if($user["admin"]===true): ?>

    <small class="tip white"><b>Your location info:</b> <?php
	if($profile["private_location"] == 1) echo _("Private. Nobody but you can access your location info.");
	elseif($profile["private_location"] == 2) echo _("Share only among registered users on the website.");
	elseif($profile["private_location"] == 3) {
	    echo _("Location info is open and public through widgets.");
	    ?> <a href="#">Share your location on a blog or web site.</a><?php
	}
	?><small>
    
    <?php endif; /* only for admins end... */ ?>
    
<?php endif; ?>

<div class="clear"></div>
<br/><br/>

<?php if($user["id"] == $profile["id"]): ?>
	<small class="tip white"><em><?php echo _("This is your profile as others see it."); ?> &mdash; <a href="#" onclick="open_page('settings'); return false;"><?php echo _("Edit your profile"); ?></a></em></small>
<?php endif; ?>




<?php endif; ?>