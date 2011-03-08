<?php

echo info_sign("This feature is under development and visible only for admins.",false);

#$lines = gather_log();

?><h2><?php echo _("Log"); ?></h2>

<div style="width: 650px;">
<ul class="history">
<?php
	echo '<li><br /><br />'.info_sign(_("Recorder hasn't recorded anything yet."),false).'<br /><br /></li>';
?>
</ul>
</div>