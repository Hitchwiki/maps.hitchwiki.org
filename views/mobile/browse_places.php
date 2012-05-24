
		<div data-role="header" data-theme="e">
			<?= $ui_home_btn; ?>
			<h1><?php echo _("Browse places"); ?></h1>
		</div>
		
		<div data-role="content">
		
			<p>
			<ul data-role="listview" data-inset="true" data-filter="true">
				<?php list_continents("li", false); ?>
			</ul>
			</p>

		</div><!-- /content -->
		
		<!-- footer -->
		<div data-role="footer" data-theme="e" data-id="search_footer" data-position="fixed">		
			<div data-role="navbar" data-iconpos="left">
				<ul>
					<li><a href="#searchpage" data-icon="search" data-transition="none"><?php echo _("Search"); ?></a></li>
					<li><a href="#browse_places" data-icon="search" data-transition="none" class="ui-btn-active"><?php echo _("Browse"); ?></a></li>
					<li><a href="#nearby_places" data-icon="locate" data-transition="none"><?php echo _("Nearby"); ?></a></li>
				</ul>
			</div><!-- /navbar -->
		</div><!-- /footer -->
