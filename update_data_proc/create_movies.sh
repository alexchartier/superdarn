a=1
for i in *.png; do
  new=$(printf "%04d$i.png" "$a") #04 pad to length of 4
  mv -i -- "$i" "$new"
  let a=a+1
done

ffmpeg  -f image2 -r 18 -pattern_type glob -i '*.png' -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2"  -pix_fmt yuv420p  ../jul_14.mp4


