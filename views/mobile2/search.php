<?php

	function search_footer($tab='searchpage') {

	?>
		<!-- footer -->
		<div data-role="footer" data-theme="e" data-id="search_footer" data-position="fixed">		
			<div data-role="navbar" data-iconpos="left">
				<ul>
					<li><a href="./?page=search#searchpage" data-icon="search" data-transition="none"<?php if($tab=="searchpage") echo ' class="ui-btn-active"'; ?>><?= _("Search"); ?></a></li>
					<li><a href="./?page=search#browse_places" data-icon="search" data-transition="none"<?php if($tab=="browse_places") echo ' class="ui-btn-active"'; ?>><?= _("Browse"); ?></a></li>
					<li><a href="./?page=search#nearby_places" data-icon="locate" data-transition="none"<?php if($tab=="nearby_places") echo ' class="ui-btn-active"'; ?>><?= _("Nearby"); ?></a></li>
				</ul>
			</div><!-- /navbar -->
		</div><!-- /footer -->
	
	<?php
	}
?>


<!-- Search -->

	<div data-role="page" id="searchpage" data-title="Hitchwiki <?php echo _("Maps")." - "._("Search"); ?>">
			
		<div data-role="header" data-theme="e">
			<?= $ui_home_btn; ?>
			<h1><?php echo _("Search"); ?></h1>
		</div>
		
		<div data-role="content">

			<div data-role="fieldcontain">
			  	<input type="search" name="query" id="query"
			  	       value="" placeholder="Search for places"
			  	       autocomplete="off"/>
			</div>
			<ul data-role="listview" data-inset="true" id="search_results"></ul> 
			
		</div><!-- /content -->

		<?php search_footer("searchpage"); ?>
	
	</div><!-- /page -->



<!-- Browse places -->

	<div data-role="page" id="browse_places" data-title="Hitchwiki <?php echo _("Maps")." - "._("Browse places"); ?>">

		<div data-role="header" data-theme="e">
			<?= $ui_home_btn; ?>
			<h1><?php echo _("Browse places"); ?></h1>
		</div>
		
		<div data-role="content">
			
			<p>
			<ul data-role="listview" data-filter="true" class="placelist" id="placelist_continent"></ul>
			</p>

		</div><!-- /content -->

		<?php search_footer("browse_places"); ?>
		
	</div><!-- /page -->

	<!-- Browse places - countries -->
	<div data-role="page" id="browse_places_country" data-title="Hitchwiki <?php echo _("Maps")." - "._("Browse places"); ?>" data-add-back-btn="true" data-back-btn-text="<?= _("Continents"); ?>">
		<div data-role="header" data-theme="e">
			<h1 id="selected_continent"><?php echo _("Browse places"); ?></h1>
	        <a href="./#mappage" data-role="button" data-icon="locate" class="ui-btn-right"><?= _("Show on map"); ?></a>
		</div>
		
		<div data-role="content">

			<p>
			<ul data-role="listview" data-divider-theme="e" data-filter="true" class="placelist" id="placelist_country"></ul>
			</p>

		</div><!-- /content -->

		<?php search_footer("browse_places"); ?>
		
	</div><!-- /page -->

	<!-- Browse places - cities -->
	<div data-role="page" id="browse_places_city" data-title="Hitchwiki <?php echo _("Maps")." - "._("Browse places"); ?>" data-add-back-btn="true" data-back-btn-text="<?= _("Countries"); ?>">
		<div data-role="header" data-theme="e">
			<h1 id="selected_country"><?php echo _("Browse places"); ?></h1>
	        <a href="./#mappage" data-role="button" data-icon="locate" class="ui-btn-right"><?= _("Show on map"); ?></a>
		</div>
		
		<div data-role="content">
		    
			<p>
			<ul data-role="listview" data-divider-theme="e" data-filter="true" class="placelist" id="placelist_city"></ul>
			</p>

		</div><!-- /content -->

		<?php search_footer("browse_places"); ?>
		
	</div><!-- /page -->



<!-- Nearby places -->

	<div data-role="page" id="nearby_places" data-title="Hitchwiki <?php echo _("Maps")." - "._("Nearby places"); ?>">
		<div data-role="header" data-theme="e">
			<?= $ui_home_btn; ?>
			<h1><?php echo _("Nearby places"); ?></h1>
		</div>
		
		<div data-role="content">
			
			<form>
			   <label for="km_slider">Kilometers:</label>
			   <input type="range" name="km_slider" id="km_slider" value="30" min="1" max="100" data-theme="e" />
			</form>

			<ul data-role="listview" data-inset="true" id="search_results"></ul> 

		</div><!-- /content -->

		<?php search_footer("nearby_places"); ?>
		
	</div><!-- /page -->