<?php

include "db.inc.php";
include "jpgraph/jpgraph.php";
include "jpgraph/jpgraph_line.php";
include "jpgraph/jpgraph_canvas.php";

$graphwidth = $_GET['w'] ? $_GET['w'] : 700;
$startdate = mysql_escape_string($_GET['start']);


$query = "SELECT * FROM stats_main WHERE date > '$startdate' ORDER BY date";
$res = mysql_query($query);


$lastlh = 0;
$lasthb = 0;

$lh = $hb = array();
while ($row = mysql_fetch_array($res)) {
    if ($lastlh) {
        $lh[$row['date']] = $row['liftershalte'] - $lastlh;
        $hb[$row['date']] = $row['hitchbase'] - $lasthb;;
    }
    $lastlh = $row['liftershalte'];
    $lasthb = $row['hitchbase'];
}
/*
print_r($lh);
print_r($hb);
// */

$p = array();
$g = new Graph($graphwidth, 200, 'auto');
$g->SetMargin(50,116,20,60);
$g->SetScale(textlin, 0, 100);
$g->xaxis->SetTickLabels(array_keys($lh));
$g->xaxis->SetLabelAngle(45);
$g->xaxis->SetFont(FF_ARIAL, FS_NORMAL, 8);
$g->xaxis->SetTextLabelInterval(4, 3);
$g->legend->Pos(0.01, 0.1);

$phb = new LinePlot(array_values($hb));
$phb->SetWeight(1);
$phb->SetLegend("Hitchbase");
$phb->SetColor("#FF0000");

$plh = new LinePlot(array_values($lh));
$plh->SetWeight(2);
$plh->SetLegend("Liftershalte");
$plh->SetColor("#00BB00");

// $g->img->SetAntiAliasing();
// $g->Add($phb);
$g->Add($plh);


$g->xaxis->scale->ticks->Set(1);
$g->yaxis->scale->ticks->Set(10);
$g->Stroke();

?>
