	<div data-role="page" class="type-interior" id="mappage" data-title="Hitchwiki <?php echo _("Maps"); ?>">

		<div data-role="content">

		  <div id="map"></div>
		  
		</div><!-- /content -->
		
		<!-- Map UI Navigation elements -->
		<div data-role="footer" data-theme="e">		
			<div data-role="navbar" data-iconpos="left">
				<ul>
					<li>
					<?php /*
					<label for="select-choice-1" class="select"><?php echo _("Map"); ?></label>
					<select name="select-choice-1" id="select-choice-1">
						<option value="yksi">yksi</option>
						<option value="kaksi">kaksi</option>
					</select>
					*/ ?>
					<a href="#layerspage" data-icon="layers" data-transition="flip"><?php echo _("Map"); ?></a>
					</li>
					<li><a href="#" id="init_add_place" data-icon="plus"><?php echo _("Add"); ?></a></li>
					<li><a href="#more" data-icon="grid"><?php echo _("More"); ?></a></li>
				</ul>
			</div><!-- /navbar -->
		</div><!-- /footer -->
		
		<div id="zoom_navigation" data-role="controlgroup" data-type="vertical">
			<a href="#" data-role="button" data-icon="plus" id="plus" data-iconpos="notext" data-theme="e"></a>
			<a href="#" data-role="button" data-icon="minus" id="minus" data-iconpos="notext" data-theme="e"></a>
		</div>
		<a href="./?page=search" id="search" data-icon="search" data-role="button" data-iconpos="notext" data-theme="e"><?php echo _("Search"); ?></a>
		<a href="#" id="locate" data-icon="locate" data-iconpos="notext" data-role="button" data-theme="e"><?php echo _("Locate me"); ?></a>
		<!-- /Map UI Navigation elements -->
		
	</div><!-- /page -->

	
	<!-- Map layers -->
	<div data-role="page" id="layerspage" data-title="Hitchwiki <?php echo _("Maps")." - "._("Choose map"); ?>">
		<div data-role="header" data-theme="e">
			<?= $ui_home_btn; ?>
			<h1><?php echo _("Choose map"); ?></h1>
		</div>
		<div data-role="content">
			<ul data-role="listview" data-inset="true" data-theme="d" id="layerslist">
			</ul>
		</div>
	</div><!-- /page -->
	
	<?php 
	
	// Add place
	include("pages/add_place.php");

	// More links
	include("pages/more.php"); 
	
	?>