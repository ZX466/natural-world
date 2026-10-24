(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();

  // --- Chart: 转向路线工作量 ---
  var stages = ['V0 收口', 'V1 渲染壳', 'V2 实况', 'V3 对齐', 'V3.5 内容包', 'V4a 挖放', 'V4-3D', 'V5 存档'];
  var days = [0.5, 2.5, 2.5, 2.5, 2.5, 4, 10, 4];
  var colors = days.map(function(d, i) { return i >= 5 ? accent2 : accent; });
  var c2 = echarts.init(document.getElementById('chart-roadmap'), null, { renderer: 'svg' });
  c2.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' }, appendToBody: true,
      formatter: function(p) {
        var i = p[0].dataIndex;
        var tag = i >= 5 ? '（V3 收官后另出）' : '';
        return p[0].name + '<br/>预估 ' + days[i] + ' 个工作日' + tag;
      }
    },
    grid: { left: 40, right: 50, top: 20, bottom: 40 },
    xAxis: {
      type: 'category', data: stages,
      axisLabel: { color: ink, fontSize: 12, interval: 0, rotate: 20 },
      axisLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'value', name: '工作日',
      nameTextStyle: { color: muted },
      axisLabel: { color: muted },
      splitLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'bar', data: days.map(function(v, i) { return { value: v, itemStyle: { color: colors[i] } }; }),
      barWidth: '52%',
      itemStyle: { borderRadius: [4, 4, 0, 0] },
      label: { show: true, position: 'top', color: ink, fontFamily: 'JetBrains Mono', fontSize: 12 }
    }]
  });
  window.addEventListener('resize', function() { c2.resize(); });
})();
