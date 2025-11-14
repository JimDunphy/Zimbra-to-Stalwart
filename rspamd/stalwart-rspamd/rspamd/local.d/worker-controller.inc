#
# step 0:
#   uncomment these out, and comment out the entries in step 3
#password = "changeMe";
#enable_password = "changeMe";
# step 1:
#   % docker compose up -d
#
# step 2:
# run the following with the password:
#   % docker exec -it rspamd rspamadm pw
#
# step 3:
# comment out the clear text passwords above and paste the result of docker exec -it rspamd rspamadm to the following and uncomment out
password = "$2$xix4yh59r3z1ikkeiqzcrty7si9qhcpeujn$tpfoz595akr96s7ixafdh7mej6pyrhijdni7rdggm3mu95dghfxy"
enable_password = "$2$xix4yh5kkadaf9r3z1eiqzcrty7si9qhcpeujn$tpfoz595akr96s7ixafdh7mej6pyrhijdni7rdggm3mu95dghfxy"
#
# step 4:
#  % docker compose up -d
#
