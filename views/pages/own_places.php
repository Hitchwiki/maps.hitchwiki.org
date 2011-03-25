<?php
/*
 * Hitchwiki Maps: own_places.php
 */
 


echo '<h2 class="icon world">'._("Own places").'</h2>';

// Show only when logged in
if($user["logged_in"]===true): ?>





<?php 
// Not logged in?
else: 
	error_sign(_("You must be logged in to edit settings."), false);
endif;

?>