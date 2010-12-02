<?php

include 'db.inc.php';
include "jpgraph/jpgraph.php";
include "jpgraph/jpgraph_line.php";
include "jpgraph/jpgraph_canvas.php";

$graphwidth = $_GET['w'] ? $_GET['w'] : 700;
$startdate = mysql_escape_string($_GET['start']);

$start = isset($_GET['top']) ? intval($_GET['top']) : 0;
$cnt = isset($_GET['cnt']) ? intval($_GET['cnt']) : 10;

$colors = array(
                "#00BBFF",
                "#0000FF",
                "#00BB00",
                "#FF00FF",
                "#00FFBB",
                "#FF0000", 
                "#AAAA00",
                "#FF9D01",
                "#013DFF",
                "#AAAAAA",
                "#FFBB00",
                "#BB0BBB",
                "#AABBDD",
                "#0088FF",
                "#FF0099",
                );

// get top 5 countries
$query = "SELECT country 
            FROM stats_countries 
           WHERE country <> 'unknown'
        GROUP BY country
        ORDER BY MAX(count) DESC
        LIMIT $start, $cnt
        ";

$top = array();

$res = mysql_query($query) or die (mysql_error());
while ($row = mysql_fetch_array($res)) {
    $top[] = $row['country'];
}
$topstr = implode("', '", $top);

$v = array();
$dates = array();



$query = "SELECT * 
            FROM stats_countries c, stats_main m
           WHERE c.fk_stats_main_id = m.id 
             AND country in ('$topstr')
             AND date > '$startdate'
         /*  AND date >= DATE_SUB(NOW(), INTERVAL 24 WEEK) */
        ORDER BY date,country
            ";

$max = 0;
$res = mysql_query($query) or die (mysql_error());
while ($row = mysql_fetch_array($res)) {
    $v[$row['country']][$row['date']] = $row['count'];
    $dates[] = $row['date'];
    if (intval($row['count']) > $max)
        $max = $row['count'];
}
$dates = array_unique($dates);
foreach($v AS $key => $val) {
    foreach($dates AS $d) {
        if (!isset($val[$d])) {
            $v[$key][$d] = 0;
        }
    }
    ksort($v[$key]);
}


// print_r($v);

$p = array();
$g = new Graph($graphwidth, 500, 'auto');
$g->SetMargin(50,135,30,60);
$g->SetScale(textlin, 0, $max);
$g->xaxis->SetTickLabels(array_keys($v[$top[0]]));
$g->xaxis->SetLabelAngle(45);
$g->xaxis->SetFont(FF_ARIAL, FS_NORMAL, 8);
$g->xaxis->SetTextLabelInterval(4, 3);
$g->legend->Pos(0.01, 0.1);


$i = 0;
foreach($top AS $c) {
    $p[$c] = new LinePlot(array_values($v[$c]));
    $p[$c]->SetWeight(2);
    $p[$c]->SetLegend($c);
    $p[$c]->SetColor($colors[($start + $i++) % count($colors)]);
    $g->Add($p[$c]);
}


$g->xaxis->scale->ticks->Set(1);
$g->yaxis->scale->ticks->Set(20);
$g->Stroke();

?>
