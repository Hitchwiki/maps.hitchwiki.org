<?php
include "db.inc.php";


/* 3 pixels per day */
// $w = 2.7*(date("z")+date("y")*365 - date("z", "2007-04-18") - 7*365);
$w = 1200;

$startdate = date('Y-m-d', strtotime('-1 year'));

?>
<html>
    <head>
        <meta http-equiv="content-type" content="text/html; charset=utf-8"/>
            <style type='text/css'>
            .active {
                background-color: #EEE;
            }
            .inactive {
                background-color: #EEE;
                color: #999;
            }
            </style>
    </head>
    <body>
<table><tr><td>
<table border='0' cellpadding='1'>
    <tr style='font-weight: bold; background-color: #AAF;'>
        <td>#</td>
        <td>Country</td>
        <td>Points</td>
    </tr>
<?php
$count = 0;
$cc = 0;
$res = mysql_query("SELECT country, count(*) AS cnt
                    FROM t_points 
                    WHERE type=1
                    GROUP BY country
                    ORDER BY cnt DESC;
                    ");
while($r = mysql_fetch_row($res)) {
    $cc++;
    $r[0] = getCountryFromCode($r[0]);
    echo "<tr style='background-color: #EEE;'><td>$cc</td><td>";
    echo implode("</td><td>", $r); 
    echo "</td></tr>";
    $count += $r[1];
}

$hbcnt = file_get_contents('/tmp/hb.cnt');
?>
</table>
</td><td valign='top'>
    <table border='0' cellpadding='1'>
        <tr style='font-weight: bold; background-color: #AAF;'>
            <td>Country</td>
            <td>City</td>
            <td>Points</td>
        </tr>
    <?php
    $res = mysql_query("SELECT country, locality AS city, count(*) AS cnt
                        FROM t_points 
                        WHERE type=1
                        GROUP BY country, city
                        ORDER BY cnt DESC
                        LIMIT $cc
                        ");
    while($r = mysql_fetch_row($res)) {
        echo "<tr style='background-color: #EEE;'><td>";
        echo implode("</td><td>", $r); 
        echo "</td></tr>";
    }

    ?>
    </table>
</td></tr>
</table>
    <br />    Anzahl nach L&auml;ndern:                     <br />    
        <img src='countrygraph.php?start=<?= $startdate ?>&w=<?= $w ?>&top=0&cnt=10' />    
        <img src='countrygraph.php?start=<?= $startdate ?>&w=<?= $w ?>&top=4&cnt=20' />    
        <!--
    <br />    Anzahl gegenueber hitchbase:              <br />    <img src='hbgraph.php?start=<?= $startdate ?>&w=<?= $w ?>' />
    -->
    <br />    Wachstum (neue Punkte pro Woche):            <br />    <img src='growgraph.php?start=<?= $startdate ?>&w=<?= $w ?>' />
    <!--
    <br />    relative Anzahl gegenueber hitchbase:     <br />    <img src='hbrelgraph.php?start=<?= $startdate ?>&w=<?= $w ?>' /> -->
    <br />
Gesamt: <?php echo $count ?> Punkte <br />
Hitchbase: <?= $hbcnt; ?> Punkte <br />
<b><?php echo round(($count/$hbcnt)*100,2) ?>%</b>
    </body>
</html>
