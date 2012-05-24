<?php
/* Hitchwiki - maps
 * Functions for mobile versions only
 * - mobilePageDiv()
 */


/* 
 * Print out div with right classes for mobile pages
 */
function mobilePageDiv($page_id, $classes=array()) {
	global $page;
	
	if($page_id == $page) array_push($classes, 'current');
	
	$classes = '';
	foreach($classes as $class) {
		$classes .= $class.' ';
	}
	$classes = trim($classes);
	
	$html = '<div id="'..'"';
	if(!empty($classes)) $html .= ' class="'.$classes.'"';
	$html .= '>';
	
	return $html;
}


?>