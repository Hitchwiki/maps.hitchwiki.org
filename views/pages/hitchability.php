<h2><?php echo _("Hitchability"); ?></h2>

<!-- hitchability -->
<h3 class="icon chart_bar"><?php echo _("Hitchability"); ?> - <?php echo _("Vote distribution"); ?></h3>
<?php echo rating_chart_html(rating_stats(), '450px', 'big'); ?>
<p><?php 
	$total = hitchability_votes_total();
	printf(ngettext("%d vote in total.", "%d votes in total.", $total), $total);
?></p>
<!-- /hitchability -->


<div class="align_left" style="margin: 0 40px 20px 0;">

	<!-- top countries -->
	<h3 class="icon world"><?php echo 'Most hitchable countries'; ?></h3>
	<table class="infotable" cellspacing="0" cellpadding="0">
		<thead>
			<tr>
				<th><?php echo _("Country"); ?></th>
				<th><?php echo _("Places"); ?></th>
			</tr>
		</thead>
		<tbody>
			<?php list_countries("tr", "markers", 10); ?>
		</tbody>
	</table>
	<!-- /top countries -->
	
</div>