var t = undefined;

function rfc3339ToDate(val) {
    var pattern = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?(?:[Tt](\d{2}):(\d{2}):(\d{2})(?:\.(\d*))?)?([Zz])?(?:([+-])(\d{2}):(\d{2}))?$/;
 
    var m = pattern.exec(val);
    var year = new Number(m[1] ? m[1] : 0);
    var month = new Number(m[2] ? m[2]-1 : 0);
    var day = new Number(m[3] ? m[3] : 0);
    var hour = new Number(m[4] ? m[4] : 0);
    var minute = new Number(m[5] ? m[5] : 0);
    var second = new Number(m[6] ? m[6] : 0);
    var millis = new Number(m[7] ? m[7] : 0);
    var gmt = m[8];
    var dir = m[9];
    var offhour = new Number(m[10] ? m[10] : 0);
    var offmin = new Number(m[11] ? m[11] : 0);
 
    if (dir && offhour && offmin) {
        var offset = ((offhour * 60) + offmin);
        if (dir == "+") {
            minute -= offset;
        } else if (dir == "-") {
            minute += offset;
        }
    }
 
    return new Date(Date.UTC(year, month, day, hour, minute, second, millis));
}
 
// zeropad a number to two digits
function pad(v) {
    if (v < 10) {
        v = "0" + v;
    }
    return v;
}

function formatFriendFeedDate(ffdate) {
    var m = new Array('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic');
    var d = rfc3339ToDate(ffdate);
    return d.getDate() + '/' + m[d.getMonth()] + ', ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}


function cometClient(id, cursor) {
    var url = "http://friendfeed-api.com/v2/updates/feed/" + id + "?callback=?&timeout=5";
    if (cursor) {
        url += "&cursor==" + cursor;
    }
    $.getJSON(url, function (data) {
        $.each(data.entries, function(i, entry) {
            $('#ff').prepend(_getLi(entry.body, entry.from.id, entry.date));
        });
        t = setTimeout(function() {cometClient(id, data.realtime.cursor)}, 2000);
    });
}

var users = {};
var frmInput = "<div class='share'><form method='post' action='?' onsubmit='post();return false;'><input type='text' id='body' name='body' style='width:300px'/><input id='submit' type='submit' value='Post'/></form></div>";
function list(id) {
    var txt = '';
    $.getJSON("http://friendfeed-api.com/v2/feed/" + id + "?callback=?",
        function (data) {
            $('#ff').html('');
            $.each(data.entries, function(i, entry) {
                users[entry.from.id] = entry.from.id;
                txt+= _getLi(entry.body, entry.from.id, entry.date);
            }); 
            $("#ff").html(txt);
            if (logged) {
                $('#inputForm').html(frmInput);
            }
            $('#txtCanal').html(chanels[id]);

            cometClient(id);
        });
}

function _getLi(body, user, date) {
    var fDade = formatFriendFeedDate(date);
    return "<li class='status'><span class='thumb vcard author'><img height='50' width='50' src='http://friendfeed-api.com/v2/picture/" + user + "?size=medium' alt='" + user + "'/></span><span class='status-body'>" + user + " : " + body + "<span class='meta entry-meta'>" + fDade + "</span></span></li>";    
}

function populateChanels() {
    $.each(chanels, function(i, chanel) {
        $('#chanels').append("<li class='status'><a class='chanelsLink' href='#' onclick='start(\"" + i + "\")'>" + chanel + "</a></li>");
    });
}
var selectedChanel;
function start(group) {
    $('#body').val('');
    selectedChanel = group;
    if (t) {
        clearTimeout(t);
    }
    $('#ff').html('<img src="/ajax-loader.gif" alt="loader"/>... cargando ' + chanels[group]);

    list(group);
}

var logged;

function checkFfLogin() {
    $.post("/oauth/check", {}, function (data) {
        if (data.redirect) {
            logged = false;
        } else {
            if (data.ok && data.ok==1) {
                logged = true;
            }
        }
        
        if (logged == true) {
            $('#login').html('');
        } else {
            $('#login').html("<a href='" + data.redirect + "'><img border='0' src='/sign-in-with-friendfeed.png' alt='Sign in with FriendFeed'></a>");
        }
        populateChanels();
    }, "json");
}
function message(txt) {
    $.blockUI({
        message: txt,
        fadeIn: 700,
        fadeOut: 700,
        css: {
            width: '350px',
            border: 'none',
            padding: '33px',
            backgroundColor: '#000',
            '-webkit-border-radius': '10px',
            '-moz-border-radius': '10px',
            opacity: .6,
            color: '#fff'
        }
    });
}

function post() {
    message('actualizando canal ...');
    var body = $('#body').val();
    $('#inputForm').html('<img src="/ajax-loader.gif" alt="loader"/>');
    $.post("a/entry", { body: body, to: selectedChanel }, function (data) {
        $.unblockUI();
        if (data.redirect) {
            message('A ocurrido un error. Recargando página.');
            window.location = data.redirect;
        }
        $('#inputForm').html(frmInput);
        }, "json");
}